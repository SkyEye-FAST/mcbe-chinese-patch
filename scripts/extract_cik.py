"""CIK Key Extractor for Minecraft: Bedrock Edition.

This script extracts CIK (Content Identity Key) keys required for decrypting
GDK (Game Development Kit) packages of Minecraft Bedrock Edition.

The script uses CikExtractor tool to dump CIK keys from the local system.
CikExtractor must be manually configured in the tools/CikExtractor directory.

Requirements:
    - Windows operating system
    - Administrator privileges
    - Valid Minecraft license on this machine
    - Python with Qiling installed (required by CikExtractor)
    - CikExtractor.exe in tools/CikExtractor/ directory
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import orjson

from cik import CikError, validate_cik


MINECRAFT_PACKAGES = {
    "microsoft.minecraftuwp_8wekyb3d8bbwe",
    "microsoft.minecraftwindowsbeta_8wekyb3d8bbwe",
}


def minecraft_key_ids(output: str) -> set[str]:
    """Collect every Release/Preview key from CikExtractor's package tree."""
    identifiers = set()
    minecraft = False
    for line in output.splitlines():
        if package := re.search(r"\b[A-Za-z0-9.]+_[A-Za-z0-9_.]+\b", line):
            minecraft = package.group().lower() in MINECRAFT_PACKAGES
        elif minecraft:
            identifiers.update(
                guid.lower()
                for guid in re.findall(
                    r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", line
                )
            )
    return identifiers


def extract_cik_keys(tools_dir: Path, cik_output_dir: Path) -> bool:
    """Extract CIK keys using CikExtractor.

    Args:
        tools_dir (Path): Directory containing CikExtractor tool
        cik_output_dir (Path): Directory where CIK keys will be saved

    Returns:
        bool: True if extraction successful, False otherwise
    """
    cikextractor_exe = tools_dir / "CikExtractor" / "CikExtractor.exe"

    if sys.platform != "win32":
        print("\nError: CIK extraction requires Windows")
        print("CikExtractor is a Windows-only tool")
        return False

    if not cikextractor_exe.exists():
        print("\nError: CikExtractor.exe not found")
        print(f"Expected location: {cikextractor_exe}")
        print("\nPlease manually download CikExtractor from:")
        print("  https://github.com/LukeFZ/CikExtractor/releases")
        print(f"Extract to: {tools_dir / 'CikExtractor'}")
        print("\nNote: Do NOT use the pre-built binaries from GitHub Releases")
        print("      as they may have issues. Build from source if possible.")
        return False

    cik_output_dir.mkdir(parents=True, exist_ok=True)

    print("\nExtracting CIK keys using CikExtractor...")
    print(f"Output directory: {cik_output_dir.absolute()}")

    cikextractor_dir = cikextractor_exe.parent

    try:
        with tempfile.TemporaryDirectory(prefix=".cik-", dir=cik_output_dir.parent) as temporary:
            dumped = Path(temporary)
            result = subprocess.run(
                [str(cikextractor_exe), "dump", "-c", str(dumped.absolute())],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                cwd=str(cikextractor_dir),
            )
            # Tool output contains device/content keys. Never echo it to logs.
            if result.returncode != 0:
                print(f"\nCikExtractor failed with error code {result.returncode}")
                return False

            identifiers = minecraft_key_ids(result.stdout)
            if not identifiers:
                raise CikError("No Minecraft Release or Preview CIKs found in local licenses")
            keys = {}
            for guid in sorted(identifiers):
                cik_file = dumped / f"{guid}.cik"
                if not cik_file.is_file():
                    raise CikError(f"CikExtractor could not export Minecraft CIK {guid}")
                data = cik_file.read_bytes()
                keys[validate_cik(guid, data)] = data

            for guid, data in keys.items():
                (cik_output_dir / f"{guid}.cik").write_bytes(data)
                print(f"  - {guid}.cik ({len(data)} bytes)")
            secret_path = cik_output_dir.parent / "minecraft-cik-keys.json"
            staged_secret = dumped / "minecraft-cik-keys.json"
            staged_secret.write_bytes(
                orjson.dumps({guid: data.hex() for guid, data in keys.items()})
            )
            staged_secret.replace(secret_path)

        print(f"\nSaved {len(keys)} Minecraft CIKs to {secret_path}")
        print("Set GitHub secret MINECRAFT_CIK_KEYS to the contents of this ignored file.")
        return True

    except FileNotFoundError:
        print(f"\nError: Could not find CikExtractor.exe at {cikextractor_exe}")
        print("Please ensure CikExtractor is properly installed")
        return False
    except (CikError, OSError) as e:
        print(f"\nFailed to run CikExtractor: {e}")
        return False


def main() -> None:
    """Main entry point for CIK key extraction."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    tools_dir = base_dir / "extracted" / "tools"
    cik_dir = tools_dir / "Cik"

    print("=" * 60)
    print("CIK Key Extractor for Minecraft: Bedrock Edition")
    print("=" * 60)
    print(f"\nBase directory: {base_dir}")
    print(f"Tools directory: {tools_dir}")
    print(f"CIK output directory: {cik_dir}")

    tools_dir.mkdir(exist_ok=True)

    success = extract_cik_keys(tools_dir, cik_dir)

    print("\n" + "=" * 60)
    if success:
        print("CIK extraction completed successfully!")
        print(f"\nCIK keys saved to: {cik_dir}")
        print("\nThese keys can be used with XvdTool.Streaming to decrypt")
        print("GDK packages (.msixvc files) of Minecraft Bedrock Edition.")
    else:
        print("CIK extraction failed.")
        print("Please check the messages above and verify:")
        print(" - You are on Windows with Administrator rights")
        print(" - CikExtractor.exe is in tools/CikExtractor/")
        print(" - .NET 9 Runtime and Python 3.11 with Qiling are installed")
        print(" - Minecraft is installed and licensed on this machine")

    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
