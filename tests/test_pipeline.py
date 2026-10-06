"""Small, offline contracts for the extraction-to-resource-pack pipeline."""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import convert
import extract
import merge
import pack
import update_sources

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    """Write a JSON fixture, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_languages(directory, value="base"):
    """Create language and JSON fixtures for every required language."""
    for language in extract.TARGET_LANGUAGES:
        path = directory / "vanilla" / language
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"shared={value}", encoding="utf-8")
        write_json(path.with_suffix(".json"), {"shared": value})


def write_package(path, value="base", extra=False, missing_language=False):
    """Build an app package fixture with optional stale or missing content."""
    with zipfile.ZipFile(path, "w") as archive:
        for language in (
            extract.TARGET_LANGUAGES[:2] if missing_language else extract.TARGET_LANGUAGES
        ):
            archive.writestr(f"data/resource_packs/vanilla/texts/{language}", f"shared={value}")
        if extra:
            archive.writestr("data/resource_packs/experimental_old/texts/en_US.lang", "old=old")
        archive.writestr(
            "data/resource_packs/vanilla_base/texts/en_US.lang", "## optional empty pack"
        )


class PipelineContracts(unittest.TestCase):
    """Verify extraction, merging, translation filtering, and packaging."""

    def setUp(self):
        """Create an isolated workspace and capture command output."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(self.output))

    def test_lang_conversion_and_duplicate_keys_keep_first(self):
        """Round-trip language entries while retaining the first duplicate key."""
        raw = "\ufeff## heading\r\n key = first=part\t# context\r\nkey=second\r\n\r\nempty=\n"
        cleaned = convert.clean_lang_content(raw)
        data = convert.convert_lang_to_json(cleaned)
        self.assertEqual(data, {"key": "first=part", "empty": ""})
        self.assertEqual(convert.convert_lang_to_json(convert.convert_json_to_lang(data)), data)
        self.assertNotIn("key=second", cleaned)

    def test_merge_priority_is_deterministic_and_channels_are_separate(self):
        """Apply stable pack priority and isolate beta and preview content."""
        source = self.root / "extracted/development"
        # Deliberately create directories in reverse lexical order.
        packs = {
            "experimental_z": {"experimental": "z", "shared": "z"},
            "experimental_a": {"experimental": "a", "shared": "a"},
            "vanilla": {"shared": "vanilla"},
            "oreui": {"shared": "oreui", "ui": "ui"},
            "previewapp": {"preview_only": "preview"},
            "beta": {"beta_only": "beta"},
            "beta/vanilla": {"nested_beta": "beta"},
        }
        for name, data in packs.items():
            write_json(source / name / "en_US.json", data)
        for channel in ("beta", "preview"):
            files = [
                source / name / "en_US.json" for name in merge.get_target_subdirs(source, channel)
            ]
            merged = merge.merge_lang_files(files)
            self.assertEqual(merged["shared"], "vanilla")
            self.assertEqual(merged["experimental"], "a")
            self.assertEqual("beta_only" in merged, channel == "beta")
            self.assertEqual("nested_beta" in merged, channel == "beta")
            self.assertEqual("preview_only" in merged, channel == "preview")

    def test_current_source_filters_stale_keys_without_source_mapping(self):
        """Keep only nonempty translations for keys in the current source."""
        source = self.root / "source.tsv"
        translation = self.root / "translation.tsv"
        convert.save_tsv_file(
            source, ["Key", "Source string"], [["experimental", "x"], ["blank", "b"]]
        )
        convert.save_tsv_file(
            translation,
            ["Key", "Translation"],
            [
                ["experimental", "translated"],
                ["experimental", "duplicate"],
                ["blank", ""],
                ["obsolete", "stale"],
            ],
        )
        self.assertEqual(
            convert.extract_current_translations(translation, source),
            {"experimental": "translated"},
        )

    def prepare_old_extraction(self):
        """Create previous extraction outputs and return their version record."""
        for folder in ("release", "development"):
            write_languages(self.root / "extracted" / folder, "old")
        write_json(
            self.root / "versions.json", {"versions": {"release": "old", "development": "old"}}
        )
        return (self.root / "versions.json").read_bytes()

    def test_every_extraction_stage_failure_preserves_outputs_and_versions(self):
        """Preserve published data when any extraction stage fails."""
        for stage in ("version", "download", "unpack", "validation"):
            with self.subTest(stage=stage):
                old_versions = self.prepare_old_extraction()

                def version(package_type):
                    if stage == "version" and package_type == "Preview":
                        return None
                    return ("new", "UWP", package_type)

                def download(package_type, directory):
                    if package_type == "Preview" and stage == "download":
                        return None
                    path = directory / f"{package_type}.appx"
                    if package_type == "Preview" and stage == "unpack":
                        path.write_bytes(b"broken archive")
                    else:
                        write_package(
                            path,
                            "new",
                            missing_language=package_type == "Preview" and stage == "validation",
                        )
                    return path

                with (
                    patch.object(
                        extract, "get_latest_version_from_api", side_effect=version
                    ) as metadata,
                    patch.object(extract, "get_appx_file", side_effect=download),
                ):
                    with self.assertRaises(RuntimeError):
                        extract.extract_languages(self.root, max_attempts=2)
                    self.assertEqual(metadata.call_count, 4)
                self.assertEqual((self.root / "versions.json").read_bytes(), old_versions)
                for folder in ("release", "development"):
                    extract.validate_extraction(self.root / "extracted" / folder)
                    self.assertEqual(
                        (self.root / "extracted" / folder / "vanilla/en_US.lang").read_text(),
                        "shared=old",
                    )
                self.assertFalse(list((self.root / "extracted").glob(".extract-*")))

    def test_retry_restarts_both_targets_and_removes_obsolete_files(self):
        """Retry both targets from clean staging and remove obsolete outputs."""
        self.prepare_old_extraction()
        # A complete successful extraction also replaces a damaged version record.
        (self.root / "versions.json").write_bytes(b"broken JSON")
        obsolete = self.root / "extracted/release/obsolete.txt"
        obsolete.write_text("old", encoding="utf-8")
        downloads = []

        def download(package_type, directory):
            attempt = len(downloads) // 2
            path = directory / f"{package_type}.appx"
            if attempt == 1:
                self.assertFalse(downloads[0].exists())
                self.assertFalse((directory.parent / "release/experimental_old").exists())
            downloads.append(path)
            if attempt == 0 and package_type == "Preview":
                path.write_bytes(b"broken")
            else:
                write_package(path, f"attempt{attempt}", extra=attempt == 0)
            return path

        with (
            patch.object(
                extract, "get_latest_version_from_api", return_value=("new", "UWP", "family")
            ) as metadata,
            patch.object(
                extract,
                "get_appx_file",
                side_effect=lambda family, directory: download(
                    "Release" if len(downloads) % 2 == 0 else "Preview", directory
                ),
            ),
        ):
            extract.extract_languages(self.root, max_attempts=2)
        self.assertEqual(metadata.call_count, 4)
        self.assertEqual(len(downloads), 4)
        self.assertFalse(obsolete.exists())
        self.assertFalse((self.root / "extracted/release/experimental_old").exists())
        self.assertEqual(extract.read_versions(self.root), {"release": "new", "development": "new"})
        self.assertEqual(
            (self.root / "extracted/release/vanilla/en_US.lang").read_text(), "shared=attempt1"
        )
        self.assertTrue(all(not path.exists() for path in downloads))

    def test_publish_failure_rolls_back_both_directories(self):
        """Restore both published targets and versions after a rename failure."""
        old_versions = self.prepare_old_extraction()
        staging = self.root / "extracted/staging"
        for folder in ("release", "development"):
            write_languages(staging / folder, "new")
        original = Path.replace

        def replace(path, destination):
            if path == staging / "development":
                raise OSError("simulated rename failure")
            return original(path, destination)

        with patch.object(Path, "replace", replace), self.assertRaises(OSError):
            extract.publish_extraction(self.root, staging, {"release": "new", "development": "new"})
        self.assertEqual((self.root / "versions.json").read_bytes(), old_versions)
        for folder in ("release", "development"):
            self.assertEqual(
                (self.root / "extracted" / folder / "vanilla/en_US.lang").read_text(), "shared=old"
            )

    def test_lightweight_check_skips_download_and_detects_incomplete_outputs(self):
        """Detect changed versions or missing outputs without downloading packages."""
        old_versions = self.prepare_old_extraction()
        with (
            patch.object(
                extract, "get_latest_version_from_api", return_value=("old", "UWP", "family")
            ),
            patch.object(extract, "get_appx_file") as download,
        ):
            self.assertFalse(extract.check_for_updates(self.root))
            (self.root / "extracted/development/vanilla/zh_TW.json").unlink()
            self.assertTrue(extract.check_for_updates(self.root))
            download.assert_not_called()
        with patch.object(
            extract, "get_latest_version_from_api", return_value=("new", "UWP", "family")
        ):
            self.assertTrue(extract.check_for_updates(self.root))
        self.assertEqual((self.root / "versions.json").read_bytes(), old_versions)

    def test_extractor_cli_exits_nonzero_when_upstream_fails(self):
        """Report upstream failure through the extractor command's exit status."""
        code = (
            "import runpy, sys; from unittest.mock import patch; import requests; "
            "sys.path.insert(0, 'scripts'); sys.argv = ['extract.py']; "
            "mock = patch('requests.get', side_effect=requests.RequestException('offline')); "
            "mock.start(); runpy.run_path('scripts/extract.py', run_name='__main__')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Extraction failed after 5 attempts", result.stderr)

    def test_missing_pipeline_inputs_raise(self):
        """Reject missing inputs at each downstream pipeline stage."""
        with self.assertRaises(FileNotFoundError):
            merge.process_target(merge.TARGETS[0], self.root)
        with self.assertRaises(FileNotFoundError):
            update_sources.process_target("release", self.root)
        with self.assertRaises(FileNotFoundError):
            pack.main(self.root)

    def test_minimal_fixture_builds_all_valid_resource_packs(self):
        """Build every resource pack with valid manifests and current translations."""
        shutil.copytree(ROOT / "resources", self.root / "resources")
        write_json(
            self.root / "versions.json", {"versions": {"release": "1.0", "development": "1.1"}}
        )
        package = self.root / "fixture.appx"
        write_package(package)
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr(
                "data/resource_packs/experimental_fixture/texts/en_US.lang", "experimental=source"
            )
        for folder in ("release", "development"):
            destination = self.root / "extracted" / folder
            self.assertTrue(
                extract.export_files_to_structure(
                    package, destination, extract.TARGET_LANGUAGES, folder == "release"
                )
            )
            extract.validate_extraction(destination)
        for target in merge.TARGETS:
            merge.process_target(target, self.root)
            update_sources.process_target(target["name"], self.root)
        languages = json.loads(
            (self.root / "resources/texts/languages.json").read_text(encoding="utf-8")
        )
        for branch in pack.BRANCHES:
            directory = self.root / "patched" / branch
            directory.mkdir(parents=True)
            (directory / "stale.lang").write_text("obsolete=bad", encoding="utf-8")
            for language in languages:
                convert.save_tsv_file(
                    directory / f"{language}.tsv",
                    ["Key", "Translation"],
                    [
                        ["shared", "translated"],
                        ["experimental", "kept"],
                        ["obsolete", "removed"],
                    ],
                )
        pack.main(self.root)
        archives = list((self.root / "packed").glob("*.mcpack"))
        self.assertEqual(len(archives), 3)
        self.assertEqual(len(list((self.root / "packed").glob("*.zip"))), 3)
        for path in archives:
            self.assertEqual(path.read_bytes(), path.with_suffix(".zip").read_bytes())
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                expected = {"manifest.json", "texts/languages.json", "texts/language_names.json"}
                expected.update(f"texts/{language}.lang" for language in languages)
                self.assertEqual(set(archive.namelist()), expected)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["format_version"], 2)
                uuid.UUID(manifest["header"]["uuid"])
                self.assertEqual(manifest["modules"][0]["type"], "resources")
                for language in languages:
                    data = convert.convert_lang_to_json(
                        archive.read(f"texts/{language}.lang").decode("utf-8")
                    )
                    self.assertEqual(data, {"shared": "translated", "experimental": "kept"})


if __name__ == "__main__":
    unittest.main()
