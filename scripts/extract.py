"""Minecraft: Bedrock Edition Language File Extractor.

This script downloads Minecraft Bedrock Edition packages and extracts
language files from them, converting .lang files to both .lang and .json formats.
Supports both UWP (appx) and GDK (msixvc) package formats.
"""

import datetime
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import TypedDict

import orjson
import requests
from bs4 import BeautifulSoup, Tag
from convert import clean_lang_content, convert_lang_to_json


class PackageInfo(TypedDict):
    """Package information dictionary structure.

    Attributes:
        package_type (str): The package type ("Release" or "Preview")
        folder_name (str): The output folder name for extracted files
    """

    package_type: str
    folder_name: str


PACKAGE_INFO: list[PackageInfo] = [
    {"package_type": "Release", "folder_name": "release"},
    {"package_type": "Preview", "folder_name": "development"},
]

TARGET_LANGUAGES: list[str] = ["en_US.lang", "zh_CN.lang", "zh_TW.lang"]


class VersionData(TypedDict):
    """Version data from bedrock.json API.

    Attributes:
        Type (str): Package type ("Release" or "Preview")
        BuildType (str): Build type ("UWP" or "GDK")
        ID (str): Version ID
        Date (str): Release date
        Variations (list): List of architecture variations
    """

    Type: str
    BuildType: str
    ID: str
    Date: str
    Variations: list[dict]


def get_latest_version_from_api(package_type: str) -> tuple[str, str, str] | None:
    """Get the latest version info from mcappx.com API.

    Args:
        package_type (str): "Release" or "Preview"

    Returns:
        tuple[str, str, str] | None: (version, build_type, download_url_or_family_name)
            For UWP: returns package family name
            For GDK: returns direct download URL
            Returns None if not found
    """
    print(f"Fetching latest {package_type} version from mcappx.com API...")

    try:
        response = requests.get("https://data.mcappx.com/v2/bedrock.json", timeout=30)
        response.raise_for_status()
        data = response.json()

        versions_data = data.get("From_mcappx.com", {})

        latest_version: str | None = None
        latest_data: VersionData | None = None
        latest_date: str = ""

        for version, version_data in versions_data.items():
            if version_data.get("Type") == package_type:
                version_date = version_data.get("Date", "")
                if version_date >= latest_date:
                    latest_date = version_date
                    latest_version = version
                    latest_data = version_data

        if not latest_version or not latest_data:
            print(f"No {package_type} version found in API")
            return None

        build_type = latest_data.get("BuildType", "UWP")
        print(f"Found {package_type} version: {latest_version} ({build_type})")

        if build_type == "GDK":
            variations = latest_data.get("Variations", [])
            for variation in variations:
                if variation.get("Arch") == "x64":
                    metadata = variation.get("MetaData", [])
                    if metadata and isinstance(metadata[0], str) and metadata[0].startswith("http"):
                        return (latest_version, build_type, metadata[0])

            print(f"No x64 GDK download URL found for {latest_version}")
            return None

        if package_type == "Release":
            family_name = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
        else:
            family_name = "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"

        return (latest_version, build_type, family_name)

    except requests.RequestException as e:
        print(f"Error fetching version info from API: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error parsing API response: {e}", file=sys.stderr)
        return None


def save_version_info(
    base_dir: Path,
    appx_files: list[tuple[str, Path]] | None = None,
) -> None:
    """Save current version information to versions.json file.

    Args:
        base_dir: Base directory where versions.json will be created
        appx_files: List of tuples (folder_name, appx_file_path) for extracting MS Store versions
    """
    pass


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

    url: str = "https://store.rg-adguard.net/api/GetFiles"
    data: dict[str, str] = {
        "type": "PackageFamilyName",
        "url": package_name,
        "ring": "RP",
        "lang": "en-US",
    }

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

        link_text: str = link.get_text(strip=True)
        if re.search(r"x64.*\.appx\b", link_text):
            appx_path: Path = base_dir / link_text
            href_value = link.get("href")

            if not isinstance(href_value, str):
                continue

            download_url: str = href_value

            print(f"Downloading {link_text}...")

            if appx_path.exists():
                print(f"Already exists, skipping {link_text}")
                return appx_path

            try:
                with requests.get(download_url, stream=True, timeout=60) as r:
                    r.raise_for_status()

                    total_size: int = int(r.headers.get("content-length", 0))
                    downloaded_size: int = 0
                    is_github_actions: bool = bool(os.getenv("GITHUB_ACTIONS"))
                    last_progress_logged: int = -1

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


def _process_lang_file(
    zip_file: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    base_output_dir: Path,
) -> bool:
    """Process a single language file from zip archive.

    Args:
        zip_file: Open ZipFile object
        entry: ZipInfo entry for the language file
        base_output_dir: Base output directory for extracted files

    Returns:
        bool: True if file was successfully processed, False otherwise
    """
    relative_path = entry.filename.replace("data/resource_packs/", "").replace("/texts/", "/")

    print(f"  Processing: {entry.filename}")

    raw_content = zip_file.read(entry).decode("utf-8", errors="ignore")
    cleaned_content = clean_lang_content(raw_content)

    if not cleaned_content:
        return False

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

    return True


def export_files_to_structure(
    zip_path: Path, base_output_dir: Path, target_languages: list[str], exclude_beta: bool = False
) -> bool:
    """Extract language files from package to directory structure.

    Args:
        zip_path (Path): Path to the appx/zip file to extract from
        base_output_dir (Path): Base output directory for extracted files
        target_languages (list[str]): List of language files to extract (e.g., ['en_US.lang'])
        exclude_beta (bool): Whether to exclude beta paths (for release packages)

    Returns:
        bool: True if any files were successfully extracted, False otherwise
    """
    package_type = "release files" if exclude_beta else "files to directory structure"
    print(f"Extracting {package_type} from {zip_path}...")

    found_any: bool = False

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_file:
            texts_entries: list[zipfile.ZipInfo] = [
                entry
                for entry in zip_file.infolist()
                if entry.filename.startswith("data/resource_packs/")
                and "/texts/" in entry.filename
                and entry.filename.endswith(".lang")
            ]
            texts_entries.sort(key=lambda x: x.filename)

            for entry in texts_entries:
                filename: str = Path(entry.filename).name

                if filename not in target_languages:
                    continue

                relative_path: str = entry.filename.replace("data/resource_packs/", "").replace(
                    "/texts/", "/"
                )

                if exclude_beta and "beta/" in relative_path:
                    print(f"  Skipping beta path: {relative_path}")
                    continue

                if _process_lang_file(zip_file, entry, base_output_dir):
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
    return export_files_to_structure(zip_path, base_output_dir, target_languages, exclude_beta=True)


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
            print(f"\r  Downloaded: {downloaded_mb:.1f} MB", end="", flush=True)

    return last_logged


def download_file(url: str, output_path: Path) -> bool:
    """Download a file from URL with progress reporting.

    Args:
        url (str): URL to download from
        output_path (Path): Path to save the downloaded file

    Returns:
        bool: True if download successful, False otherwise
    """
    print(f"Downloading from {url}...")

    if output_path.exists():
        print(f"File already exists: {output_path.name}")
        return True

    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()

            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            is_github_actions = bool(os.getenv("GITHUB_ACTIONS"))
            last_progress_logged = -1

            with output_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        last_progress_logged = _show_download_progress(
                            downloaded_size, total_size, last_progress_logged, is_github_actions
                        )

            if not is_github_actions:
                print()
        return True

    except requests.RequestException as e:
        print(f"Error downloading file: {e}", file=sys.stderr)
        if output_path.exists():
            output_path.unlink()
        return False


def download_gdk_package(download_url: str, base_dir: Path, version: str) -> Path | None:
    """Download GDK package (msixvc) from direct URL.

    Args:
        download_url (str): Direct download URL for the GDK package
        base_dir (Path): Base directory to save the downloaded file
        version (str): Version string for filename

    Returns:
        Path: Path to the downloaded file, or None if download failed
    """
    filename = f"Microsoft.MinecraftWindowsBeta_{version}_x64__8wekyb3d8bbwe.msixvc"
    if "Release" in download_url or "MinecraftUWP" in download_url:
        filename = f"Microsoft.MinecraftUWP_{version}_x64__8wekyb3d8bbwe.msixvc"

    output_path = base_dir / filename

    if download_file(download_url, output_path):
        return output_path

    return None


def process_gdk_package(msixvc_file: Path, base_output_dir: Path) -> bool:
    """Process GDK package using CikExtractor and XvdTool.Streaming.

    Args:
        msixvc_file (Path): Path to the msixvc file
        base_output_dir (Path): Base output directory for extracted files

    Returns:
        bool: True if processing successful, False otherwise
    """
    print(f"Processing GDK package: {msixvc_file.name}")

    tools_dir = base_output_dir.parent / "tools"
    tools_dir.mkdir(exist_ok=True)

    cikextractor_exe = tools_dir / "CikExtractor" / "CikExtractor.exe"
    xvdtool_exe = tools_dir / "XvdTool.Streaming" / "XvdTool.Streaming.exe"
    cik_dir = tools_dir / "Cik"
    cik_dir.mkdir(exist_ok=True)

    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

    if not is_ci:
        if sys.platform != "win32":
            print("\nError: GDK package processing requires Windows")
            print("CikExtractor and XvdTool.Streaming are Windows-only tools")
            return False

        print("\nChecking for required tools...")

        if not cikextractor_exe.exists():
            print("\nError: CikExtractor.exe not found")
            print("Please manually download CikExtractor from:")
            print("  https://github.com/LukeFZ/CikExtractor/releases")
            print(f"Extract to: {tools_dir / 'CikExtractor'}")
            return False

        if not xvdtool_exe.exists():
            print("\nError: XvdTool.Streaming.exe not found")
            print("Please manually download XvdTool.Streaming from:")
            print("  https://github.com/LukeFZ/XvdTool.Streaming/releases")
            print(f"Extract to: {tools_dir / 'XvdTool.Streaming'}")
            return False
    else:
        if not xvdtool_exe.exists():
            print(f"\nError: XvdTool.Streaming.exe not found at {xvdtool_exe}")
            return False

    if is_ci:
        print("Running in CI environment")
        cik_secret = os.environ.get("MINECRAFT_CIK")
        cik_guid = os.environ.get("MINECRAFT_CIK_GUID")

        if not cik_secret or not cik_guid:
            print("\nWarning: MINECRAFT_CIK or MINECRAFT_CIK_GUID environment variables not set")
            print("GDK package processing requires a valid CIK key")
            print("Please set these secrets in your GitHub repository settings")
            print("Skipping GDK package processing...")
            return False

        print("Using CIK from environment variables")
        cik_file = cik_dir / f"{cik_guid}.cik"

        try:
            cik_bytes = bytes.fromhex(cik_secret)
            cik_file.write_bytes(cik_bytes)
            print(f"CIK file created: {cik_file.name}")
        except Exception as e:
            print(f"Failed to create CIK file: {e}")
            return False

    else:
        print("\nStep 1: Extracting CIK using CikExtractor...")

        cikextractor_dir = cikextractor_exe.parent

        try:
            result = subprocess.run(
                [str(cikextractor_exe), "dump", "-c", str(cik_dir.absolute())],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cikextractor_dir),
            )

            print(f"CikExtractor return code: {result.returncode}")

            if result.stdout:
                print("CikExtractor output:")
                print(result.stdout)

            if result.stderr:
                print("CikExtractor errors:")
                print(result.stderr)

            if result.returncode != 0:
                print(f"CikExtractor failed with error code {result.returncode}")
                print("\nNote: CikExtractor requires:")
                print("  - Administrator privileges")
                print("  - Valid Minecraft license on this machine")
                print("  - Python with Qiling installed")
                return False

            cik_files = list(cik_dir.glob("*.cik"))
            if not cik_files:
                print("\nWarning: No CIK files were extracted")
                print("This usually means:")
                print("  - Minecraft is not installed/licensed on this machine")
                print("  - The required game version is not installed")
                print("For CI/automated builds, use environment variables instead")
                return False

            print(f"\nCIK extraction successful - {len(cik_files)} key(s) extracted:")
            for cik_file in cik_files:
                print(f"  - {cik_file.name}")

        except Exception as e:
            print(f"Failed to run CikExtractor: {e}")
            return False

    print("\nStep 2: Decrypting and extracting package using XvdTool.Streaming...")

    extract_output_dir = base_output_dir / "temp_extract"
    extract_output_dir.mkdir(exist_ok=True)

    xvdtool_working_dir = extract_output_dir / "xvdtool_workspace"
    xvdtool_working_dir.mkdir(exist_ok=True)

    xvd_cik_dir = xvdtool_working_dir / "Cik"
    xvd_cik_dir.mkdir(exist_ok=True)

    cik_files_copied = 0
    for cik_file in cik_dir.glob("*.cik"):
        dest_cik = xvd_cik_dir / cik_file.name
        shutil.copy2(cik_file, dest_cik)
        print(f"Copied CIK: {cik_file.name}")
        cik_files_copied += 1

    if cik_files_copied == 0:
        print("Warning: No CIK files found to copy")
        return False

    try:
        result = subprocess.run(
            [
                str(xvdtool_exe),
                "extract",
                str(msixvc_file.absolute()),
                "-o",
                str(extract_output_dir.absolute()),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(xvdtool_working_dir),
        )

        if result.returncode != 0:
            print(f"XvdTool.Streaming failed with error code {result.returncode}")
            if result.stderr:
                print(f"Error output:\n{result.stderr}")
            if result.stdout:
                print(f"Standard output:\n{result.stdout}")
            return False

        print("Package extraction successful")

        if result.stdout:
            print("XvdTool.Streaming output:")
            for line in result.stdout.splitlines():
                print(f"  {line}")

        if result.stderr:
            print("XvdTool.Streaming errors/warnings:")
            for line in result.stderr.splitlines():
                print(f"  {line}")

    except Exception as e:
        print(f"Failed to run XvdTool.Streaming: {e}")
        return False

    print("\nStep 3: Organizing extracted files...")

    data_folder = None
    for candidate in ["data", "Data", "DATA"]:
        candidate_path = extract_output_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            data_folder = candidate_path
            break

    if not data_folder:
        print("Warning: Could not find 'data' folder in extracted files")
        print(f"Contents of {extract_output_dir}:")
        for item in extract_output_dir.iterdir():
            print(f"  - {item.name}")
        return False

    resource_packs_dir = data_folder / "resource_packs"
    if not resource_packs_dir.exists():
        print(f"Warning: Could not find resource_packs folder in {data_folder}")
        return False

    print(f"Processing language files from {resource_packs_dir}...")

    found_any = False
    target_languages = ["en_US.lang", "zh_CN.lang", "zh_TW.lang"]

    for pack_dir in resource_packs_dir.iterdir():
        if not pack_dir.is_dir():
            continue

        texts_dir = pack_dir / "texts"
        if not texts_dir.exists():
            continue

        for lang_file_name in target_languages:
            lang_file = texts_dir / lang_file_name
            if not lang_file.exists():
                continue

            raw_content = lang_file.read_text(encoding="utf-8", errors="ignore")
            cleaned_content = clean_lang_content(raw_content)

            if not cleaned_content:
                continue

            relative_path = f"{pack_dir.name}/{lang_file_name}"
            output_file = base_output_dir / relative_path
            output_file.parent.mkdir(parents=True, exist_ok=True)

            output_file.write_text(cleaned_content, encoding="utf-8", newline="\n")
            print(f"  Created {relative_path}")

            json_data = convert_lang_to_json(cleaned_content)
            json_file = output_file.with_suffix(".json")

            with json_file.open("wb") as f:
                f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))

            json_relative_path = relative_path.replace(".lang", ".json")
            print(f"  Created {json_relative_path} with {len(json_data)} entries")

            found_any = True

    if not found_any:
        print("Warning: No language files found in resource packs")
        print(f"Please manually check: {resource_packs_dir}")
        return False

    shutil.rmtree(extract_output_dir, ignore_errors=True)

    print("\nGDK package processing completed successfully!")
    return True


def main() -> None:
    """Main entry point for the language file extractor."""
    script_dir: Path = Path(__file__).parent
    base_dir: Path = script_dir.parent

    output_dir: Path = base_dir / "extracted"
    output_dir.mkdir(exist_ok=True)

    print("Starting language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    package_files: list[tuple[str, Path, str]] = []
    version_info: dict[str, str | None] = {"release": None, "development": None}

    for i, package in enumerate(PACKAGE_INFO):
        prefix: str = "\n" if i == 0 else "\n\n"
        package_type = package["package_type"]
        folder_name = package["folder_name"]

        print(f"{prefix}Processing package type: {package_type}")

        version_data = get_latest_version_from_api(package_type)

        if not version_data:
            print(f"Failed to get version info for {package_type}")
            continue

        version, build_type, download_info = version_data

        if folder_name == "release":
            version_info["release"] = version
        else:
            version_info["development"] = version

        package_file: Path | None = None

        if build_type == "UWP":
            package_file = get_appx_file(download_info, base_dir)
        elif build_type == "GDK":
            package_file = download_gdk_package(download_info, base_dir, version)
        else:
            print(f"Unknown build type: {build_type}")
            continue

        if not package_file:
            print(f"Failed to download package for {package_type}")
            continue

        print(f"Downloaded: {package_file.name}")
        package_files.append((folder_name, package_file, build_type))

    print("\n" + "=" * 60)
    versions_file = base_dir / "versions.json"
    version_data_to_save = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "versions": version_info,
    }

    tmp_file = versions_file.with_suffix(versions_file.suffix + ".tmp")
    tmp_file.write_bytes(orjson.dumps(version_data_to_save, option=orjson.OPT_INDENT_2))
    tmp_file.replace(versions_file)

    print("Version information saved:")
    print(f"  Release: {version_info.get('release', 'N/A')}")
    print(f"  Development: {version_info.get('development', 'N/A')}")

    for folder_name, package_file, build_type in package_files:
        print("\n" + "=" * 60)
        package_output_dir = output_dir / folder_name
        package_output_dir.mkdir(exist_ok=True)

        if build_type == "GDK":
            success = process_gdk_package(package_file, package_output_dir)
            if not success:
                print(f"GDK package processing not yet fully implemented for {package_file}")
        else:
            is_release = folder_name == "release"
            if is_release:
                success = export_release_files(package_file, package_output_dir, TARGET_LANGUAGES)
            else:
                success = export_files_to_structure(
                    package_file, package_output_dir, TARGET_LANGUAGES
                )

            if not success:
                print(f"Failed to extract language files from {package_file}")

    print("\n" + "=" * 60)
    print("Language file extraction completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")


if __name__ == "__main__":
    main()
