"""Minecraft Bedrock Edition resource pack packer.

This module converts translation data from TSV format to Minecraft lang files
and packages them into distributable resource packs. The process involves:

1. Reading TSV files from the sources directory containing translation data
2. Converting TSV data to Minecraft .lang format using convert module functions
3. Generating version-specific resource pack archives (.zip and .mcpack)

The module supports multiple branches (release, beta, preview) with different
versioning schemes and automatically organizes output files in the packed directory.
"""

import json
import shutil
import zipfile
from pathlib import Path

from convert import extract_translation_from_tsv, save_lang_file


def format_version(version_str: str, is_dev: bool = False) -> str:
    """Format version string according to branch requirements.

    Args:
        version_str (str): Version string in format "x.y.z.w"
        is_dev (bool, optional): Whether this is a development build. Defaults to False.

    Returns:
        str: Formatted version string.
    """
    x, y, z, _ = version_str.split(".")
    z_int = int(z)

    if is_dev:
        new_z = z_int // 100
        new_w = z_int % 100
        return f"{x}.{y}.{new_z}.{new_w}"
    else:
        new_z = z_int // 100
        return f"{x}.{y}.{new_z}"


def create_pack_archive(branch: str, lang_files: list[Path], version: str) -> None:
    """Create zip and mcpack files for a branch.

    Args:
        branch (str): The branch name (e.g., "release", "beta", "preview")
        lang_files (list[Path]): List of language file paths to include
        version (str): Version string for the pack filename
    """
    output_dir = Path("packed")
    output_dir.mkdir(exist_ok=True)

    pack_dir = output_dir / f"temp_{branch}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2("resources/manifest.json", pack_dir / "manifest.json")

        texts_dir = pack_dir / "texts"
        texts_dir.mkdir(exist_ok=True)

        for lang_file in lang_files:
            shutil.copy2(lang_file, texts_dir / lang_file.name)

        languages_json = Path("resources/texts/languages.json")
        if languages_json.exists():
            shutil.copy2(languages_json, texts_dir / "languages.json")

        base_name = f"MCBE_Chinese_Patch_{branch}_{version}"
        zip_path = output_dir / f"{base_name}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in pack_dir.rglob("*"):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(pack_dir))

        shutil.copy2(zip_path, output_dir / f"{base_name}.mcpack")
        print(f"Created {base_name}.zip (.mcpack)")

    finally:
        if pack_dir.exists():
            shutil.rmtree(pack_dir)


def main() -> None:
    """Convert TSV files to lang format and create resource packs.

    Processes all TSV files in the patched directory, converts them to Minecraft
    lang format, and packages them into distributable resource packs for each branch.
    """
    print("Converting patched TSV files to lang format...")

    patched_dir = Path("patched")
    if not patched_dir.exists():
        print("Patched directory not found!")
        return

    for branch_dir in patched_dir.iterdir():
        if not branch_dir.is_dir():
            continue

        print(f"Processing branch: {branch_dir.name}")

        for tsv_file in branch_dir.glob("*.tsv"):
            print(f"  Converting {tsv_file.name}")

            translation_data = extract_translation_from_tsv(tsv_file)

            output_lang_file = tsv_file.with_suffix(".lang")
            save_lang_file(output_lang_file, translation_data)

    print("\nPacking resource packs...")

    with open("versions.json", encoding="utf-8") as f:
        versions = json.load(f)["versions"]

    for branch_dir in patched_dir.iterdir():
        if not branch_dir.is_dir():
            continue

        branch = branch_dir.name
        lang_files = list(branch_dir.glob("*.lang"))

        if not lang_files:
            print(f"No lang files found for {branch}, skipping...")
            continue

        print(f"Packing branch: {branch}")

        if branch == "release":
            version = format_version(versions["release"], False)
        else:
            version = format_version(versions["development"], True)

        create_pack_archive(branch, lang_files, version)

    print("\nDone!")


if __name__ == "__main__":
    main()
