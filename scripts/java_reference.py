"""Generate bilingual Java Edition reference TMs without touching Bedrock data."""

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import requests

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
ASSET_BASE_URL = "https://resources.download.minecraft.net"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "java-reference"
TARGET_LANGUAGES = {"zh_cn": "zh-CN", "zh_tw": "zh-TW"}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def download(session: requests.Session, url: str, sha1: str | None = None) -> bytes:
    """Download a resource and verify its SHA-1 when a digest is supplied."""
    with session.get(url, timeout=60) as response:
        response.raise_for_status()
        data = response.content
    if sha1 is not None and hashlib.sha1(data).hexdigest() != sha1:
        raise ValueError(f"SHA-1 mismatch: {url}")
    return data


def parse_language(data: bytes, name: str) -> dict[str, str]:
    """Decode a nonempty language JSON object containing only string values."""
    language = json.loads(data)
    if not isinstance(language, dict) or not language:
        raise ValueError(f"Missing or empty language resource: {name}")
    if any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in language.items()
    ):
        raise ValueError(f"Language resource must contain string values: {name}")
    return language


def fetch_languages(version: str | None = None) -> tuple[str, dict[str, dict[str, str]]]:
    """Resolve an official release; English is bundled in the client, Chinese in assets."""
    with requests.Session() as session:
        manifest = json.loads(download(session, VERSION_MANIFEST_URL))
        version_id = version if version is not None else manifest["latest"]["release"]
        release = next(
            (
                entry
                for entry in manifest["versions"]
                if entry["id"] == version_id and entry["type"] == "release"
            ),
            None,
        )
        if release is None:
            raise ValueError(f"Not an official Java Edition release: {version_id}")
        metadata = json.loads(download(session, release["url"], release["sha1"]))
        index_info = metadata["assetIndex"]
        assets = json.loads(download(session, index_info["url"], index_info["sha1"]))["objects"]

        # Resolve both targets before downloading the larger client archive.
        target_assets = {}
        for locale in TARGET_LANGUAGES:
            asset_path = f"minecraft/lang/{locale}.json"
            if asset_path not in assets:
                raise ValueError(f"Missing target language resource: {asset_path}")
            target_assets[locale] = assets[asset_path]

        client_info = metadata["downloads"]["client"]
        client = download(session, client_info["url"], client_info["sha1"])
        with ZipFile(BytesIO(client)) as archive:
            languages = {
                "en_us": parse_language(
                    archive.read("assets/minecraft/lang/en_us.json"), "en_us.json"
                )
            }
        for locale, asset in target_assets.items():
            digest = asset["hash"]
            url = f"{ASSET_BASE_URL}/{digest[:2]}/{digest}"
            languages[locale] = parse_language(download(session, url, digest), f"{locale}.json")
    return version_id, languages


def translation_pairs(source: dict[str, str], target: dict[str, str]) -> list[tuple[str, str]]:
    """Deduplicate exact pairs only; keep all different translations of a source."""
    return sorted({(text, target[key]) for key, text in source.items() if text and target.get(key)})


def build_tmx(pairs: list[tuple[str, str]], target_language: str, version: str) -> bytes:
    """Serialize exact bilingual pairs as deterministic TMX with release metadata."""
    root = ET.Element("tmx", version="1.4")
    header = ET.SubElement(
        root,
        "header",
        {
            "creationtool": "mcbe-chinese-patch-java-reference",
            "creationtoolversion": "1",
            "segtype": "block",
            "o-tmf": "Minecraft Java Edition language JSON",
            "adminlang": "en-US",
            "srclang": "en-US",
            "datatype": "plaintext",
        },
    )
    ET.SubElement(header, "prop", type="x-java-version").text = version
    body = ET.SubElement(root, "body")
    for source, target in sorted(set(pairs)):
        unit = ET.SubElement(body, "tu")
        for language, text in (("en-US", source), (target_language, target)):
            variant = ET.SubElement(unit, "tuv", {XML_LANG: language})
            ET.SubElement(variant, "seg").text = text
    ET.indent(root, space="  ")
    # No timestamps, random IDs, or Java keys: identical inputs give identical bytes.
    # XML parsers normalize literal CR/CRLF, so preserve CR as a character reference.
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data.replace(b"\r", b"&#13;") + b"\n"


def generate_reference(output_dir: Path, version: str | None = None) -> None:
    """Fetch an official release and write both independent Chinese reference TMs."""
    version_id, languages = fetch_languages(version)
    source = languages["en_us"]
    outputs = []
    for locale in TARGET_LANGUAGES:
        target = languages[locale]
        pairs = translation_pairs(source, target)
        if not pairs:
            raise ValueError(f"No translated segments for {locale}")
        matched = sum(bool(text and target.get(key)) for key, text in source.items())
        tmx = build_tmx(pairs, TARGET_LANGUAGES[locale], version_id)
        outputs.append((f"java-en-{locale}.tmx", tmx, len(pairs), len(source) - matched))

    # Finish fetching and rendering both languages before writing any output.
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Minecraft Java Edition {version_id}")
    for filename, tmx, count, skipped in outputs:
        path = output_dir / filename
        path.write_bytes(tmx)
        print(f"{path}: {count} entries; {skipped} keys skipped (missing/empty segments)")


def main() -> int:
    """Generate reference TMX files from CLI options and return an exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Pin an official release (default: latest release)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="TMX output directory (default: java-reference/)",
    )
    args = parser.parse_args()
    try:
        generate_reference(args.output_dir, args.version)
    except Exception as error:
        print(f"Java reference generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
