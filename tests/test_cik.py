"""CIK collection and GDK failure contracts, without real licenses or secrets."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cik
import extract
import extract_cik


RELEASE = "bdb9e791-c97c-3734-e1a8-bc602552df06"
PREVIEW = "1f49d63f-8bf5-1f8d-ed7e-dbd89477dad9"
OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def key_bytes(guid):
    """Create a correctly structured synthetic CIK."""
    return uuid.UUID(guid).bytes_le + bytes(range(32))


class CikContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.destination = self.root / "release"
        self.destination.mkdir()
        for name in ("XvdTool.Streaming", "CikExtractor"):
            directory = self.tools / name
            directory.mkdir(parents=True)
            (directory / f"{name}.exe").touch()
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(self.output))
        self.enterContext(patch.object(sys, "platform", "win32"))

    def configured_keys(self):
        return json.dumps({guid: key_bytes(guid).hex() for guid in (RELEASE, PREVIEW)})

    def test_collection_rejects_invalid_or_mismatched_keys_without_leaking_values(self):
        invalid_values = [
            "not-json",
            "[]",
            "{}",
            json.dumps({RELEASE: 42}),
            json.dumps({"../../bad": key_bytes(RELEASE).hex()}),
            json.dumps({RELEASE: "private-invalid-hex"}),
            json.dumps({RELEASE: bytes(range(32)).hex()}),
            json.dumps({RELEASE: key_bytes(PREVIEW).hex()}),
            json.dumps({RELEASE: key_bytes(RELEASE).hex(), RELEASE.upper(): key_bytes(RELEASE).hex()}),
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(cik.CikError) as error:
                cik.parse_cik_keys(value)
            self.assertNotIn("private-invalid-hex", str(error.exception))
            self.assertNotIn(key_bytes(RELEASE).hex(), str(error.exception))

    def test_both_keys_reach_xvdtool_and_valid_output_is_processed(self):
        def run(args, **kwargs):
            directory = Path(kwargs["cwd"]) / "Cik"
            self.assertEqual({p.stem for p in directory.glob("*.cik")}, {RELEASE, PREVIEW})
            for guid in (RELEASE, PREVIEW):
                self.assertEqual((directory / f"{guid}.cik").read_bytes(), key_bytes(guid))
            texts = Path(args[4]) / "data/resource_packs/vanilla/texts"
            texts.mkdir(parents=True)
            for language in extract.TARGET_LANGUAGES:
                (texts / language).write_text("key=value", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "Successfully extracted files.", "")

        with (
            patch.dict("os.environ", {"MINECRAFT_CIK_KEYS": self.configured_keys()}, clear=True),
            patch.object(extract.subprocess, "run", side_effect=run),
        ):
            self.assertTrue(extract.process_gdk_package(self.root / "fixture.msixvc", self.destination, self.tools))
        extract.validate_extraction(self.destination)
        self.assertFalse((self.destination / "temp_extract").exists())

    def test_missing_key_is_fatal_even_when_xvdtool_returns_zero(self):
        for stream in ("stdout", "stderr"):
            result = subprocess.CompletedProcess([], 0, "", "")
            setattr(result, stream, f"ERR: Could not find key {RELEASE} loaded in key storage.")
            with (
                self.subTest(stream=stream),
                patch.dict("os.environ", {"MINECRAFT_CIK_KEYS": self.configured_keys()}, clear=True),
                patch.object(extract.subprocess, "run", return_value=result),
                self.assertRaisesRegex(cik.CikError, RELEASE),
            ):
                extract.process_gdk_package(self.root / "fixture.msixvc", self.destination, self.tools)
        self.assertNotIn("Package extraction successful", self.output.getvalue())

    def test_empty_secret_does_not_reuse_local_keys(self):
        local = self.tools / "Cik"
        local.mkdir()
        (local / f"{RELEASE}.cik").write_bytes(key_bytes(RELEASE))
        with (
            patch.dict("os.environ", {"MINECRAFT_CIK_KEYS": ""}, clear=True),
            patch.object(extract.subprocess, "run") as run,
            self.assertRaises(cik.CikError),
        ):
            extract.process_gdk_package(self.root / "fixture.msixvc", self.destination, self.tools)
        run.assert_not_called()

    def test_missing_key_stops_retries_and_preserves_published_versions(self):
        record = self.root / "versions.json"
        record.write_text('{"versions":{"release":"old"}}', encoding="utf-8")
        with (
            patch.object(extract, "fetch_versions", return_value={"release": ("new", "GDK", "url")}),
            patch.object(extract, "download_gdk_package", return_value=self.root / "fixture.msixvc") as download,
            patch.object(extract, "process_gdk_package", side_effect=cik.CikError("Missing key")),
            self.assertRaises(cik.CikError),
        ):
            extract.extract_languages(self.root)
        download.assert_called_once()
        self.assertEqual(json.loads(record.read_text())["versions"]["release"], "old")
        self.assertFalse(list((self.root / "extracted").glob(".extract-*")))

    def test_license_export_includes_all_minecraft_keys_and_excludes_other_games(self):
        output = (
            f"├── ?? microsoft.minecraftuwp_8wekyb3d8bbwe\n│   ├── ?? {RELEASE}\n"
            f"│   │   └── Key: private-key-value\n"
            f"├── ?? unrelated.game_otherpublisher\n│   └── ?? {OTHER}\n"
            f"└── ?? microsoft.minecraftwindowsbeta_8wekyb3d8bbwe\n    └── ?? {PREVIEW}\n"
        )

        def run(args, **kwargs):
            directory = Path(args[3])
            for guid in (RELEASE, PREVIEW, OTHER):
                (directory / f"{guid}.cik").write_bytes(key_bytes(guid))
            return subprocess.CompletedProcess(args, 0, output, "")

        with patch.object(extract_cik.subprocess, "run", side_effect=run):
            self.assertTrue(extract_cik.extract_cik_keys(self.tools, self.tools / "Cik"))
        secret = (self.tools / "minecraft-cik-keys.json").read_text()
        self.assertEqual(set(cik.parse_cik_keys(secret)), {RELEASE, PREVIEW})
        self.assertFalse((self.tools / "Cik" / f"{OTHER}.cik").exists())
        self.assertNotIn("private-key-value", self.output.getvalue())
        self.assertNotIn(key_bytes(RELEASE).hex(), self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
