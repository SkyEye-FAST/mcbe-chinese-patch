"""Minecraft: Bedrock Edition Language File Merger.

This script merges multiple language JSON files from different resource packs
into consolidated files for release, beta, and preview versions.
"""

import json
import sys
from pathlib import Path
from typing import Any, TypedDict


class TargetConfig(TypedDict):
    """Target configuration structure.

    Attributes:
        name (str): The name of the target
        path (str): The relative path to the extracted files directory
    """

    name: str
    path: str


MERGE_ORDER: list[str] = [
    "vanilla",
    "experimental_*",
    "oreui",
    "persona",
    "editor",
    "chemistry",
    "education",
    "education_demo",
]

TARGETS: list[TargetConfig] = [
    {"name": "release", "path": "extracted/release"},
    {"name": "beta", "path": "extracted/development"},
    {"name": "preview", "path": "extracted/development"},
]

LANG_FILES: list[str] = ["en_US.json", "zh_CN.json", "zh_TW.json"]


def merge_lang_files(file_list: list[Path]) -> dict[str, Any]:
    """Merge multiple language JSON files into a single dictionary.

    Args:
        file_list (list[Path]): List of file paths to merge

    Returns:
        dict: Dictionary with merged language data, sorted by keys.
        First occurrence of each key wins in case of duplicates.
    """
    merged: dict[str, Any] = {}

    for file_path in file_list:
        if file_path.exists():
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if key not in merged:
                            merged[key] = value
            except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
                print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)
                continue

    return dict(sorted(merged.items()))


def get_ordered_subdirs(base_dir: Path, exclude_dirs: list[str] | None = None) -> list[str]:
    """Get subdirectories in the specified merge order.

    Args:
        base_dir (Path): Base directory to scan for subdirectories
        exclude_dirs (list[str] | None): List of directory names to exclude from processing

    Returns:
        list[str]: List of directory names ordered according to MERGE_ORDER configuration.
        Wildcard patterns (e.g., 'experimental_*') are supported.
    """
    if exclude_dirs is None:
        exclude_dirs = []

    if not base_dir.exists():
        return []

    all_dirs = [d.name for d in base_dir.iterdir() if d.is_dir() and d.name not in exclude_dirs]

    ordered: list[str] = []

    for pattern in MERGE_ORDER:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            matched = [d for d in all_dirs if d.startswith(prefix)]
            ordered.extend(matched)
        else:
            if pattern in all_dirs:
                ordered.append(pattern)

    remaining = [d for d in all_dirs if d not in ordered]
    ordered.extend(remaining)

    return ordered


def process_target(target: TargetConfig, base_dir: Path) -> None:
    """Process a single target configuration (release, beta, or preview).

    Args:
        target (TargetConfig): Target configuration containing name and path
        base_dir (Path): Base directory path for the project
    """
    src_dir = base_dir / target["path"]
    if not src_dir.exists():
        print(f"Source directory does not exist: {src_dir}")
        return

    out_dir = base_dir / "merged" / target["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if target["name"] == "beta":
        ordered_subdirs = get_ordered_subdirs(src_dir, exclude_dirs=["previewapp"])
        beta_dir = src_dir / "beta"
        if beta_dir.exists():
            beta_subdirs = get_ordered_subdirs(beta_dir)
            ordered_subdirs.extend(f"beta/{subdir}" for subdir in beta_subdirs)
    elif target["name"] == "preview":
        ordered_subdirs = get_ordered_subdirs(src_dir, exclude_dirs=["beta"])
        preview_dir = src_dir / "previewapp"
        if preview_dir.exists():
            preview_subdirs = get_ordered_subdirs(preview_dir)
            ordered_subdirs.extend(f"previewapp/{subdir}" for subdir in preview_subdirs)
    else:
        ordered_subdirs = get_ordered_subdirs(src_dir)

    for lang_file in LANG_FILES:
        file_list: list[Path] = []

        for subdir in ordered_subdirs:
            subdir_path = src_dir / subdir
            lang_path = subdir_path / lang_file
            if lang_path.exists():
                file_list.append(lang_path)

        if not file_list:
            print(f"No files found for {lang_file} in {target['name']}")
            continue

        merged_data = merge_lang_files(file_list)

        output_file = out_dir / lang_file
        try:
            with output_file.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2, sort_keys=True)

            print(f"Merged {len(file_list)} files to {output_file}")
            print(f"  Total keys: {len(merged_data)}")
            print("  Files merged:")
            for file_path in file_list:
                print(f"    {file_path}")

        except (OSError, PermissionError) as e:
            print(f"Error writing output file {output_file}: {e}", file=sys.stderr)


def main() -> None:
    """Main entry point for the language file merger."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    print("Starting language file merge process...")
    print(f"Base directory: {base_dir}")

    for target in TARGETS:
        print(f"\nProcessing target: {target['name']}")
        process_target(target, base_dir)

    merge_dir = base_dir / "merged"
    print(f"\nAll language files merged! Output: {merge_dir}")


if __name__ == "__main__":
    main()
