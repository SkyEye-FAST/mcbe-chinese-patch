"""Minecraft: Bedrock Edition Language File Extractor.

This script downloads Minecraft Bedrock Edition appx packages and extracts
language files from them, converting .lang files to both .lang and .json formats.
"""

import os
import re
import sys
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import TypedDict

import orjson
import requests
from bs4 import BeautifulSoup, Tag


class PackageInfo(TypedDict):
    """Package information dictionary structure.

    Attributes:
        name (str): The package family name
        folder_name (str): The output folder name for extracted files
    """

    name: str
    folder_name: str


PACKAGE_INFO: list[PackageInfo] = [
    {"name": "Microsoft.MinecraftUWP_8wekyb3d8bbwe", "folder_name": "release"},
    {"name": "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe", "folder_name": "development"},
]

TARGET_LANGUAGES: list[str] = ["en_US.lang", "zh_CN.lang", "zh_TW.lang"]


def _show_download_progress(
    downloaded_size: int, total_size: int, last_logged: int, is_github_actions: bool
) -> int:
    """Show download progress based on environment.

    Args:
        downloaded_size: Number of bytes downloaded
        total_size: Total file size in bytes (0 if unknown)
        last_logged: Last progress value that was logged
        is_github_actions: Whether running in GitHub Actions

    Returns:
        Updated last_logged value
    """
    downloaded_mb = downloaded_size / 1024 / 1024

    if total_size > 0:
        progress = (downloaded_size / total_size) * 100
        total_mb = total_size / 1024 / 1024

        if is_github_actions:
            current_step = int(progress // 10)
            if current_step > last_logged:
                print(f"  Progress: {progress:.0f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)")
                return current_step
        else:
            progress_text = f"\r  Progress: {progress:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
            print(progress_text, end="", flush=True)
    else:
        if is_github_actions:
            mb_int = int(downloaded_mb)
            if mb_int % 50 == 0 and mb_int > last_logged:
                print(f"  Downloaded: {downloaded_mb:.0f} MB")
                return mb_int
        else:
            progress_text = f"\r  Downloaded: {downloaded_mb:.1f} MB"
            print(progress_text, end="", flush=True)

    return last_logged


def get_appx_file(package_name: str, base_dir: Path) -> Path | None:
    """Download appx file for the specified package.

    Args:
        package_name (str): The package family name to download
        base_dir (Path): Base directory to save the downloaded file

    Returns:
        Path: Path to the downloaded appx file, or None if download failed

    This function uses the store.rg-adguard.net service to obtain download links
    for Microsoft Store packages, then downloads the x64 appx file.
    """
    print(f"Getting download link for {package_name}...")

    url = "https://store.rg-adguard.net/api/GetFiles"
    data = {"type": "PackageFamilyName", "url": package_name, "ring": "RP", "lang": "en-US"}

    try:
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error requesting download links: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue

        link_text = link.get_text(strip=True)
        if re.search(r"x64.*\.appx\b", link_text):
            appx_path = base_dir / link_text
            href_value = link.get("href")

            if not isinstance(href_value, str):
                continue

            download_url = href_value

            print(f"Downloading {link_text}...")

            if appx_path.exists():
                print(f"Already exists, skipping {link_text}")
                return appx_path

            try:
                with requests.get(download_url, stream=True, timeout=60) as r:
                    r.raise_for_status()

                    total_size = int(r.headers.get("content-length", 0))
                    downloaded_size = 0
                    is_github_actions = bool(os.getenv("GITHUB_ACTIONS"))
                    last_progress_logged = -1

                    with appx_path.open("wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                last_progress_logged = _show_download_progress(
                                    downloaded_size,
                                    total_size,
                                    last_progress_logged,
                                    is_github_actions,
                                )

                    if not is_github_actions:
                        print()
                return appx_path
            except requests.RequestException as e:
                print(f"Error downloading {link_text}: {e}", file=sys.stderr)
                return None

    print(f"No x64 appx file found for {package_name}")
    return None


def convert_lang_to_json(lang_content: str) -> OrderedDict[str, str]:
    """Convert .lang file content to JSON-compatible ordered dictionary.

    Args:
        lang_content (str): Content of the .lang file as a string

    Returns:
        OrderedDict: JSON-compatible ordered dictionary representation of the lang file.

    The function parses Minecraft .lang files which use key=value format,
    ignoring empty lines and comments starting with ##.
    """
    json_data: OrderedDict[str, str] = OrderedDict()

    for line in lang_content.splitlines():
        line = line.strip(" \t\r\n\f\v")  # Keep U+00A0

        if not line or line.startswith("##"):
            continue

        equal_index = line.find("=")
        if equal_index > 0:
            key = line[:equal_index].strip()
            value = line[equal_index + 1 :].strip(" \t\r\n\f\v")

            if key not in json_data:
                json_data[key] = value

    return json_data


def remove_duplicate_keys(lang_content: str) -> str:
    """Remove duplicate keys from lang file content, keeping first occurrence.

    Args:
        lang_content (str): Original lang file content as a string

    Returns:
        str: Cleaned lang file content without duplicate keys.
            Comments and empty lines are preserved as-is.
    """
    seen_keys: set[str] = set()
    result_lines: list[str] = []

    for line in lang_content.splitlines():
        trimmed_line = line.strip()

        if not trimmed_line or trimmed_line.startswith("##"):
            result_lines.append(line)
            continue

        equal_index = trimmed_line.find("=")
        if equal_index > 0:
            key = trimmed_line[:equal_index].strip()

            if key not in seen_keys:
                seen_keys.add(key)
                result_lines.append(line)
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def clean_lang_content(raw_content: str) -> str:
    """Clean and normalize language file content.

    Args:
        raw_content (str): Raw content from the language file

    Returns:
        str: Cleaned content with normalized line endings and no empty lines
    """
    cleaned_content = raw_content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")

    cleaned_content = "\n".join(
        line for line in cleaned_content.splitlines() if line.strip(" \t\r\n\f\v")
    )

    return remove_duplicate_keys(cleaned_content) if cleaned_content.strip() else ""


def export_files_to_structure(
    zip_path: Path, base_output_dir: Path, target_languages: list[str]
) -> bool:
    """Extract language files from development package to directory structure.

    Args:
        zip_path (Path): Path to the appx/zip file to extract from
        base_output_dir (Path): Base output directory for extracted files
        target_languages (list[str]): List of language files to extract (e.g., ['en_US.lang'])

    Returns:
        bool: True if any files were successfully extracted, False otherwise
    """
    print(f"Extracting files to directory structure from {zip_path}...")

    found_any = False

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_file:
            texts_entries = [
                entry
                for entry in zip_file.infolist()
                if entry.filename.startswith("data/resource_packs/")
                and "/texts/" in entry.filename
                and entry.filename.endswith(".lang")
            ]
            texts_entries.sort(key=lambda x: x.filename)

            for entry in texts_entries:
                filename = Path(entry.filename).name

                if filename not in target_languages:
                    continue

                relative_path = entry.filename.replace("data/resource_packs/", "").replace(
                    "/texts/", "/"
                )

                print(f"  Processing: {entry.filename}")

                raw_content = zip_file.read(entry).decode("utf-8", errors="ignore")
                cleaned_content = clean_lang_content(raw_content)

                if not cleaned_content:
                    continue

                output_file = base_output_dir / relative_path
                output_file.parent.mkdir(parents=True, exist_ok=True)

                output_file.write_text(cleaned_content, encoding="utf-8", newline="\n")
                print(f"Created {relative_path}")

                json_data = convert_lang_to_json(cleaned_content)
                json_file = output_file.with_suffix(".json")

                with json_file.open("wb") as f:
                    f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))

                json_relative_path = relative_path.replace(".lang", ".json")
                print(f"Created {json_relative_path} with {len(json_data)} entries")

                found_any = True

    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error extracting from {zip_path}: {e}", file=sys.stderr)
        return False

    return found_any


def export_release_files(
    zip_path: Path, base_output_dir: Path, target_languages: list[str]
) -> bool:
    """Extract language files from release package, excluding beta paths.

    Args:
        zip_path (Path): Path to the appx/zip file to extract from
        base_output_dir (Path): Base output directory for extracted files
        target_languages (list[str]): List of language files to extract (e.g., ['en_US.lang'])

    Returns:
        bool: True if any files were successfully extracted, False otherwise
    """
    print(f"Extracting release files from {zip_path}...")

    found_any = False

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_file:
            texts_entries = [
                entry
                for entry in zip_file.infolist()
                if entry.filename.startswith("data/resource_packs/")
                and "/texts/" in entry.filename
                and entry.filename.endswith(".lang")
            ]
            texts_entries.sort(key=lambda x: x.filename)

            for entry in texts_entries:
                filename = Path(entry.filename).name

                if filename not in target_languages:
                    continue

                relative_path = entry.filename.replace("data/resource_packs/", "").replace(
                    "/texts/", "/"
                )

                if "beta/" in relative_path:
                    print(f"  Skipping beta path: {relative_path}")
                    continue

                print(f"  Processing: {entry.filename}")

                raw_content = zip_file.read(entry).decode("utf-8", errors="ignore")
                cleaned_content = clean_lang_content(raw_content)

                if not cleaned_content:
                    continue

                output_file = base_output_dir / relative_path
                output_file.parent.mkdir(parents=True, exist_ok=True)

                output_file.write_text(cleaned_content, encoding="utf-8", newline="\n")
                print(f"Created {relative_path}")

                json_data = convert_lang_to_json(cleaned_content)
                json_file = output_file.with_suffix(".json")

                with json_file.open("wb") as f:
                    f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))

                json_relative_path = relative_path.replace(".lang", ".json")
                print(f"Created {json_relative_path} with {len(json_data)} entries")

                found_any = True

    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error extracting from {zip_path}: {e}", file=sys.stderr)
        return False

    return found_any


def main() -> None:
    """Main entry point for the language file extractor."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    output_dir = base_dir / "extracted"
    output_dir.mkdir(exist_ok=True)

    print("Starting language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    for i, package in enumerate(PACKAGE_INFO):
        prefix = "\n" if i == 0 else "\n\n"
        print(f"{prefix}Processing package: {package['name']}")

        appx_file = get_appx_file(package["name"], base_dir)

        if not appx_file:
            print(f"Failed to download appx file for {package['name']}")
            continue

        package_output_dir = output_dir / package["folder_name"]
        package_output_dir.mkdir(exist_ok=True)

        is_release = package["name"] == "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
        if is_release:
            success = export_release_files(appx_file, package_output_dir, TARGET_LANGUAGES)
        else:
            success = export_files_to_structure(appx_file, package_output_dir, TARGET_LANGUAGES)

        if not success:
            print(f"Failed to extract language files from {appx_file}")

    print("\n\nLanguage file extraction completed!")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
