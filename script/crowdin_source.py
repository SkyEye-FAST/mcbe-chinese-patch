"""Minecraft: Bedrock Edition Source File Updater.

This script processes merged language files and creates source files with context
information for Crowdin translation platform integration.
"""

import sys
from pathlib import Path
from typing import TypedDict

import orjson


class StringWithContext(TypedDict):
    """String with translation context structure.

    Attributes:
        text (str): The original text content
        crowdinContext (str): Context information for translators
    """

    text: str
    crowdinContext: str


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
    source_data: dict[str, StringWithContext] = {}
    try:
        with source_path.open("r", encoding="utf-8") as f:
            source_content = orjson.loads(f.read())
            for k, v in source_content.items():
                source_data[k] = {"text": v, "crowdinContext": "Original Translation"}
        print(f"Loaded {len(source_content)} entries from {SOURCE_LANGUAGE}")
    except (orjson.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"Warning: Failed to read {source_path}: {e}", file=sys.stderr)
        return

    for target_file in TARGET_LANGUAGES:
        target_path = src_dir / target_file
        print(f"Processing target file: {target_path}")
        try:
            with target_path.open("r", encoding="utf-8") as f:
                target_content = orjson.loads(f.read())
                print(f"  Loaded {len(target_content)} entries from {target_file}")

                context_added = 0
                for k, v in target_content.items():
                    if k in source_data:
                        source_data[k]["crowdinContext"] += f"\n{target_file}: {v}"
                        context_added += 1

                print(f"  Added context for {context_added} entries")
        except (orjson.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to read {target_path}: {e}", file=sys.stderr)

    output_file = out_dir / SOURCE_LANGUAGE
    print(f"Writing output file: {output_file}")
    try:
        with output_file.open("wb") as f:
            # It's intended not to include orjson.OPT_SORT_KEYS
            options = orjson.OPT_INDENT_2
            f.write(orjson.dumps(source_data, option=options))

        print(f"Successfully created {output_file} with {len(source_data)} entries")
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
    print(f"\nAll language files updated! Output: {sources_dir}")


if __name__ == "__main__":
    main()
