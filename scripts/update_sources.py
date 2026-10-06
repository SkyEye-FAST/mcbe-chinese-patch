"""Minecraft: Bedrock Edition Chinese Patch Source File Updater.

This script processes merged language files and creates source files with context
information for Crowdin translation platform integration in TSV format.
"""

import csv
from pathlib import Path

from convert import load_json_file

SOURCE_LANGUAGE: str = "en_US.json"
TARGET_LANGUAGES: list[str] = ["zh_CN.json", "zh_TW.json"]

TARGETS: list[str] = ["release", "beta", "preview"]


def process_target(target: str, base_dir: Path) -> None:
    """Generate Crowdin source from all required merged languages, or fail."""
    src_dir = base_dir / "merged" / target
    source_content = load_json_file(src_dir / SOURCE_LANGUAGE)
    translations = {
        filename.removesuffix(".json"): load_json_file(src_dir / filename)
        for filename in TARGET_LANGUAGES
    }
    if not source_content or any(not data for data in translations.values()):
        raise ValueError(f"Empty merged language for {target}")

    out_dir = base_dir / "sources" / target
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / "en_US.tsv"
    with output_file.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["Key", "Source string", "Context", "Translation"])
        for string_id, source_text in source_content.items():
            context_lines = ["Original Translation"]
            for lang_code, lang_content in translations.items():
                if string_id in lang_content:
                    context_lines.append(f"{lang_code}: {lang_content[string_id]}")
            writer.writerow([string_id, source_text, "\n".join(context_lines), ""])
    print(f"Created {output_file} with {len(source_content)} entries")


def main() -> None:
    """Main entry point for the source file updater."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    print("Starting source file update process...")
    print(f"Base directory: {base_dir}")

    for target in TARGETS:
        print(f"\nProcessing target: {target}")
        process_target(target, base_dir)

    sources_dir = base_dir / "sources"
    print(f"\nAll TSV language files updated! Output: {sources_dir}")


if __name__ == "__main__":
    main()
