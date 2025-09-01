import sys
from pathlib import Path

import orjson

class StringWithContext:
    text: str
    crowdinContext: str

SOURCE_LANGUAGE: str = "en_US.json"
TARGET_LANGUAGES: list[str] = ["zh_CN.json", "zh_TW.json"]

TARGETS: list[str] = [
    "release",
    "beta",
    "preview"
]

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
    source_data: dict[str, StringWithContext] = {}
    try:
        with source_path.open("r", encoding="utf-8") as f:
            for k, v in orjson.loads(f.read()).items():
                source_data[k] = {"text": v, "crowdinContext": "Original Translation"}
    except (orjson.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"Warning: Failed to read {source_path}: {e}", file=sys.stderr)
        return


    for target_file in TARGET_LANGUAGES:
        target_path = src_dir / target_file
        try:
            with target_path.open("r", encoding="utf-8") as f:
                for k, v in orjson.loads(f.read()).items():
                    if k in source_data:
                        source_data[k]["crowdinContext"] += f"\n{target_file}: {v}"
        except (orjson.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to read {source_path}: {e}", file=sys.stderr)
    
    output_file = out_dir / SOURCE_LANGUAGE
    try:
        with output_file.open("wb") as f:
            # It's intended not to include orjson.OPT_SORT_KEYS
            options = orjson.OPT_INDENT_2
            f.write(orjson.dumps(source_data, option=options))       
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

    merge_dir = base_dir / "sources"
    print(f"\nAll language files updated! Output: {merge_dir}")


if __name__ == "__main__":
    main()
