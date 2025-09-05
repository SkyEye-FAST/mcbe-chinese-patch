"""Minecraft: Bedrock Edition Chinese Patch Source File Updater.

This script processes merged language files and creates source files with context
information for Crowdin translation platform integration in TSV format.
"""

import csv
import sys
from pathlib import Path

from convert import load_json_file

SOURCE_LANGUAGE: str = "en_US.json"
TARGET_LANGUAGES: list[str] = ["zh_CN.json", "zh_TW.json"]

TARGETS: list[str] = ["release", "beta", "preview"]


def process_target(target: str, base_dir: Path) -> None:
    """Process a single target configuration (release, beta, or preview).

    Args:
        target (str): Target name
        base_dir (Path): Base directory path for the project
    """
    src_dir = base_dir / "merged" / target
    if not src_dir.exists():
        print(f"Source directory does not exist: {src_dir}")
        return

    out_dir = base_dir / "sources" / target
    out_dir.mkdir(parents=True, exist_ok=True)

    source_path = src_dir / SOURCE_LANGUAGE
    print(f"Reading source file: {source_path}")

    try:
        source_content = load_json_file(source_path)
        print(f"Loaded {len(source_content)} entries from {SOURCE_LANGUAGE}")
    except (FileNotFoundError, PermissionError) as e:
        print(f"Warning: Failed to read {source_path}: {e}", file=sys.stderr)
        return

    translations = {}
    for target_file in TARGET_LANGUAGES:
        target_path = src_dir / target_file
        print(f"Processing target file: {target_path}")
        try:
            target_content = load_json_file(target_path)
            print(f"  Loaded {len(target_content)} entries from {target_file}")

            lang_code = target_file.replace(".json", "")
            translations[lang_code] = target_content
        except (FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to read {target_path}: {e}", file=sys.stderr)

    output_file = out_dir / SOURCE_LANGUAGE.replace(".json", ".tsv")
    print(f"Writing output file: {output_file}")

    try:
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["Key", "Source string", "Context", "Translation"])

            for string_id, source_text in source_content.items():
                context_lines = ["Original Translation"]

                for lang_code, lang_content in translations.items():
                    if string_id in lang_content:
                        context_lines.append(f"{lang_code}: {lang_content[string_id]}")

                context = "\n".join(context_lines)
                writer.writerow([string_id, source_text, context])

        print(f"Successfully created {output_file} with {len(source_content)} entries")
    except (OSError, PermissionError) as e:
        print(f"Error writing output file {output_file}: {e}", file=sys.stderr)


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
