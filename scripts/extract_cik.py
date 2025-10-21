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

import subprocess
import sys
from pathlib import Path


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
        result = subprocess.run(
            [str(cikextractor_exe), "dump", "-c", str(cik_output_dir.absolute())],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cikextractor_dir),
        )

        print(f"\nCikExtractor return code: {result.returncode}")

        if result.stdout:
            print("\nCikExtractor output:")
            print(result.stdout)

        if result.stderr:
            print("\nCikExtractor errors:")
            print(result.stderr)

        if result.returncode != 0:
            print(f"\nCikExtractor failed with error code {result.returncode}")
            return False

        minecraft_guid = None
        if result.stdout:
            lines = result.stdout.splitlines()
            for i, line in enumerate(lines):
                if "microsoft.minecraftwindowsbeta_8wekyb3d8bbwe" in line.lower():
                    for j in range(i + 1, min(i + 10, len(lines))):
                        next_line = lines[j]
                        if "└── ??" in next_line or "    └── ??" in next_line:
                            parts = next_line.strip().split()
                            if len(parts) >= 2:
                                guid_candidate = parts[-1]
                                if "-" in guid_candidate and len(guid_candidate) > 30:
                                    minecraft_guid = guid_candidate
                                    break
                    break

        cik_files = list(cik_output_dir.glob("*.cik"))
        if not cik_files:
            print("\nWarning: No CIK files were extracted")
            return False

        print(f"\nCIK extraction successful - {len(cik_files)} key(s) extracted:")
        for cik_file in cik_files:
            file_size = cik_file.stat().st_size
            print(f"  - {cik_file.name} ({file_size} bytes)")

        minecraft_cik = None
        if minecraft_guid:
            for cik_file in cik_files:
                if cik_file.stem.lower() == minecraft_guid.lower():
                    minecraft_cik = cik_file
                    break

        if minecraft_cik:
            print("\n" + "=" * 60)
            print("GitHub Actions Secrets Configuration")
            print("=" * 60)

            cik_bytes = minecraft_cik.read_bytes()
            cik_hex = cik_bytes.hex().upper()
            cik_guid = minecraft_cik.stem

            print(f"\nMinecraft CIK file: {minecraft_cik.name}")
            print("\nMINECRAFT_CIK_GUID:")
            print(cik_guid)
            print("\nMINECRAFT_CIK:")
            print(cik_hex)
        else:
            print("\nWarning: Could not identify Minecraft CIK from extracted files")
            print("Please manually check the CIK files in the output directory")

        return True

    except FileNotFoundError:
        print(f"\nError: Could not find CikExtractor.exe at {cikextractor_exe}")
        print("Please ensure CikExtractor is properly installed")
        return False
    except Exception as e:
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
