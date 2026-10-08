"""Minecraft: Bedrock Edition Language File Extractor.

This script downloads Minecraft Bedrock Edition packages and extracts
language files from them, converting .lang files to both .lang and .json formats.
Supports both UWP (appx) and GDK (msixvc) package formats.
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import TypedDict

import orjson
import requests
from bs4 import BeautifulSoup, Tag
from cik import CikError, parse_cik_keys, validate_cik
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
        headers = {
            "User-Agent": "mcappx_developer",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://mcappx.com/",
        }
        response = requests.get(
            "https://data.mcappx.com/v2/bedrock.json", headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        versions_data = data.get("From_mcappx.com", {})

        latest_version: str | None = None
        latest_data: VersionData | None = None
        latest_date = ""

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
    data = {
        "type": "PackageFamilyName",
        "url": package_name,
        "ring": "RP",
        "lang": "en-US",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30)
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
            href_value = link.get("href")
            if not isinstance(href_value, str):
                continue

            appx_path = base_dir / link_text
            if download_file(href_value, appx_path):
                return appx_path
            return None

    print(f"No x64 appx file found for {package_name}")
    return None


def _process_lang_file(
    zip_file: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    base_output_dir: Path,
) -> None:
    """Process a single language file from zip archive.

    Args:
        zip_file: Open ZipFile object
        entry: ZipInfo entry for the language file
        base_output_dir: Base output directory for extracted files

    Raises on decoding or writing errors.
    """
    relative_path = entry.filename.replace("data/resource_packs/", "").replace("/texts/", "/")

    print(f"  Processing: {entry.filename}")

    raw_content = zip_file.read(entry).decode("utf-8")
    cleaned_content = clean_lang_content(raw_content)

    _save_lang_and_json(cleaned_content, base_output_dir / relative_path, relative_path)


def _save_lang_and_json(content: str, output_file: Path, relative_path: str) -> None:
    """Save language content to .lang and .json files.

    Args:
        content: Cleaned language file content
        output_file: Path to output .lang file
        relative_path: Relative path for display purposes

    Raises on writing errors.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_file.write_text(content, encoding="utf-8", newline="\n")
    print(f"Created {relative_path}")

    json_data = convert_lang_to_json(content)
    json_file = output_file.with_suffix(".json")

    with json_file.open("wb") as f:
        f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))

    json_relative_path = relative_path.replace(".lang", ".json")
    print(f"Created {json_relative_path} with {len(json_data)} entries")


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

                if exclude_beta and "beta/" in relative_path:
                    print(f"  Skipping beta path: {relative_path}")
                    continue

                _process_lang_file(zip_file, entry, base_output_dir)
                found_any = True

    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error extracting from {zip_path}: {e}", file=sys.stderr)
        return False

    return found_any


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

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        with requests.get(url, stream=True, headers=headers, timeout=60) as r:
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
            if downloaded_size == 0 or (total_size and downloaded_size != total_size):
                raise ValueError(f"Incomplete download: {downloaded_size}/{total_size} bytes")
        return True

    except (requests.RequestException, ValueError, OSError) as e:
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


def _process_extracted_lang_files(
    resource_packs_dir: Path,
    base_output_dir: Path,
    target_languages: list[str],
    exclude_beta: bool = False,
) -> bool:
    """Process language files from extracted resource packs directory.

    Args:
        resource_packs_dir: Path to resource_packs directory
        base_output_dir: Base output directory for processed files
        target_languages: List of language files to process
        exclude_beta: Skip language files inside beta resource packs

    Returns:
        bool: True if any files were successfully processed, False otherwise
    """
    print(f"Processing language files from {resource_packs_dir}...")

    found_any = False

    for lang_file in sorted(resource_packs_dir.rglob("*.lang")):
        if lang_file.name not in target_languages or lang_file.parent.name != "texts":
            continue
        relative = lang_file.relative_to(resource_packs_dir)
        if exclude_beta and "beta" in relative.parts:
            continue
        content = clean_lang_content(lang_file.read_text(encoding="utf-8"))
        relative_path = (relative.parent.parent / lang_file.name).as_posix()
        _save_lang_and_json(content, base_output_dir / relative_path, relative_path)
        found_any = True

    return found_any


def process_gdk_package(
    msixvc_file: Path, base_output_dir: Path, tools_dir: Path, exclude_beta: bool = False
) -> bool:
    """Process GDK package using XvdTool.Streaming with pre-configured CIK keys.

    Args:
        msixvc_file (Path): Path to the msixvc file
        base_output_dir (Path): Base output directory for extracted files
        tools_dir (Path): Shared XvdTool.Streaming and CIK directory
        exclude_beta (bool): Exclude beta language files from Release

    Returns:
        bool: True if processing successful, False otherwise

    Note:
        Provide MINECRAFT_CIK_KEYS in CI, or local keys in tools/Cik/.
        Use extract_cik.py script to extract CIK keys before running this function.
    """
    print(f"Processing GDK package: {msixvc_file.name}")

    tools_dir.mkdir(exist_ok=True)

    xvdtool_exe = tools_dir / "XvdTool.Streaming" / "XvdTool.Streaming.exe"
    cik_dir = tools_dir / "Cik"

    if sys.platform != "win32":
        print("\nError: GDK package processing requires Windows")
        print("XvdTool.Streaming is a Windows-only tool")
        return False

    print("\nChecking for required tools and CIK keys...")

    if not xvdtool_exe.exists():
        print("\nError: XvdTool.Streaming.exe not found")
        print("Please manually download XvdTool.Streaming from:")
        print("  https://github.com/LukeFZ/XvdTool.Streaming/releases")
        print(f"Extract to: {tools_dir / 'XvdTool.Streaming'}")
        return False

    if (configured_keys := os.getenv("MINECRAFT_CIK_KEYS")) is not None:
        keys = parse_cik_keys(configured_keys)
    else:
        keys = {}
        for cik_file in sorted(cik_dir.glob("*.cik")):
            data = cik_file.read_bytes()
            keys[validate_cik(cik_file.stem, data)] = data
    if not keys:
        raise CikError("No CIK keys found; run extract_cik.py or set MINECRAFT_CIK_KEYS")

    print(f"Found {len(keys)} CIK key(s):")
    for guid in keys:
        print(f"  - {guid}.cik")

    print("\nDecrypting and extracting package using XvdTool.Streaming...")

    extract_output_dir = base_output_dir / "temp_extract"
    extract_output_dir.mkdir(exist_ok=True)

    xvdtool_working_dir = extract_output_dir / "xvdtool_workspace"
    xvdtool_working_dir.mkdir(exist_ok=True)

    xvd_cik_dir = xvdtool_working_dir / "Cik"
    xvd_cik_dir.mkdir(exist_ok=True)

    for guid, data in keys.items():
        (xvd_cik_dir / f"{guid}.cik").write_bytes(data)

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

        tool_output = f"{result.stdout}\n{result.stderr}"
        missing_key = re.search(
            r"Could not find key ([0-9a-fA-F-]{36}) loaded in key storage", tool_output
        )
        if missing_key:
            raise CikError(
                f"GDK package requires CIK {missing_key.group(1)}; "
                "refresh Minecraft licenses, run extract_cik.py and update MINECRAFT_CIK_KEYS"
            )
        if result.returncode != 0 or re.search(r"(?m)^\s*ERR:", tool_output):
            print(f"XvdTool.Streaming failed with error code {result.returncode}")
            if result.stderr:
                print(f"Error output:\n{result.stderr}")
            if result.stdout:
                print(f"Standard output:\n{result.stdout}")
            return False

        if result.stdout:
            print("XvdTool.Streaming output:")
            for line in result.stdout.splitlines():
                print(f"  {line}")

        if result.stderr:
            print("XvdTool.Streaming errors/warnings:")
            for line in result.stderr.splitlines():
                print(f"  {line}")

    except CikError:
        raise
    except Exception as e:
        print(f"Failed to run XvdTool.Streaming: {e}")
        return False

    print("\nOrganizing extracted files...")

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

    found_any = _process_extracted_lang_files(
        resource_packs_dir, base_output_dir, TARGET_LANGUAGES, exclude_beta
    )

    if not found_any:
        print("Warning: No language files found in resource packs")
        print(f"Please manually check: {resource_packs_dir}")
        return False

    shutil.rmtree(extract_output_dir, ignore_errors=True)

    print("\nGDK package processing completed successfully!")
    return True


def validate_extraction(directory: Path) -> None:
    """Require nonempty base languages and matching JSON, allowing empty optional packs."""
    for language in TARGET_LANGUAGES:
        path = directory / "vanilla" / language
        if not path.is_file() or not convert_lang_to_json(path.read_text(encoding="utf-8")):
            raise ValueError(f"Missing or empty required language: {path}")
    for lang_file in directory.rglob("*.lang"):
        data = convert_lang_to_json(lang_file.read_text(encoding="utf-8"))
        if data != orjson.loads(lang_file.with_suffix(".json").read_bytes()):
            raise ValueError(f"Invalid extracted language: {lang_file}")


def fetch_versions() -> dict[str, tuple[str, str, str]]:
    """Fetch both targets; missing metadata is a failed attempt."""
    versions = {}
    for package in PACKAGE_INFO:
        info = get_latest_version_from_api(package["package_type"])
        if info is None:
            raise RuntimeError(f"Failed to get version for {package['package_type']}")
        versions[package["folder_name"]] = info
    return versions


def read_versions(base_dir: Path) -> dict[str, str]:
    """Read recorded extraction versions, or return an empty mapping if absent."""
    versions_file = base_dir / "versions.json"
    if not versions_file.exists():
        return {}
    return orjson.loads(versions_file.read_bytes())["versions"]


def publish_extraction(base_dir: Path, staging: Path, versions: dict[str, str]) -> None:
    """Install complete directories with rename/rollback; commit the version record last.

    Replacing a nonempty directory requires two renames on Windows. Backups stay on
    the same filesystem until both targets and versions.json have been installed.
    """
    versions_file = base_dir / "versions.json"
    staged_versions = staging / "versions.json"
    staged_versions.write_bytes(
        orjson.dumps(
            {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "versions": versions,
            },
            option=orjson.OPT_INDENT_2,
        )
    )

    installed: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for folder in versions:
            destination = base_dir / "extracted" / folder
            backup = staging / f"old-{folder}"
            if destination.exists():
                destination.replace(backup)
                backups.append((destination, backup))
            (staging / folder).replace(destination)
            installed.append(destination)
        staged_versions.replace(versions_file)
    except Exception:
        for destination in reversed(installed):
            shutil.rmtree(destination)
        for destination, backup in reversed(backups):
            backup.replace(destination)
        raise


def extract_languages(base_dir: Path, max_attempts: int = 5) -> None:
    """Retry the entire fetch/download/extract/validate cycle in a fresh workspace."""
    output_dir = base_dir / "extracted"
    output_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_attempts + 1):
        try:
            with tempfile.TemporaryDirectory(prefix=".extract-", dir=output_dir) as temporary:
                staging = Path(temporary)
                downloads = staging / "downloads"
                downloads.mkdir()
                metadata = fetch_versions()
                for folder, (version, build_type, download_info) in metadata.items():
                    destination = staging / folder
                    destination.mkdir()
                    if build_type == "UWP":
                        package_file = get_appx_file(download_info, downloads)
                    elif build_type == "GDK":
                        package_file = download_gdk_package(download_info, downloads, version)
                    else:
                        raise ValueError(f"Unknown build type: {build_type}")
                    if package_file is None:
                        raise RuntimeError(f"Failed to download {folder}")
                    if build_type == "GDK":
                        success = process_gdk_package(
                            package_file, destination, output_dir / "tools", folder == "release"
                        )
                    else:
                        success = export_files_to_structure(
                            package_file, destination, TARGET_LANGUAGES, folder == "release"
                        )
                    if not success:
                        raise RuntimeError(f"Failed to extract {folder}")
                    validate_extraction(destination)
                versions = {folder: info[0] for folder, info in metadata.items()}
                publish_extraction(base_dir, staging, versions)
            print(f"Extraction completed: {versions}")
            return
        except CikError:
            raise
        except Exception as error:
            print(f"Extraction attempt {attempt}/{max_attempts} failed: {error}", file=sys.stderr)
    raise RuntimeError(f"Extraction failed after {max_attempts} attempts")


def check_for_updates(base_dir: Path, max_attempts: int = 5) -> bool:
    """Check upstream metadata without downloading packages or updating versions.json."""
    for attempt in range(1, max_attempts + 1):
        try:
            metadata = fetch_versions()
            latest = {folder: info[0] for folder, info in metadata.items()}
            if latest != read_versions(base_dir):
                return True
            for folder in latest:
                try:
                    validate_extraction(base_dir / "extracted" / folder)
                except (OSError, ValueError):
                    return True
            return False
        except Exception as error:
            print(f"Version check {attempt}/{max_attempts} failed: {error}", file=sys.stderr)
    raise RuntimeError(f"Version check failed after {max_attempts} attempts")


def main() -> int:
    """Run extraction or the lightweight update check and return an exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Only check whether extraction is needed"
    )
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    try:
        if args.check:
            changed = check_for_updates(base_dir)
            print(f"Extraction needed: {changed}")
            if output := os.getenv("GITHUB_OUTPUT"):
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write(f"changed={str(changed).lower()}\n")
        else:
            extract_languages(base_dir)
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
