import hashlib
import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from scripts import java_reference as reference


class JavaReferenceTests(unittest.TestCase):
    def test_tmx_escapes_text_and_keeps_language_variants(self):
        source = '<tag> & "quotes"\r\n%1$s'
        target = '中文 <字> & "引号"\r\n%1$s'
        tmx = reference.build_tmx([(source, target)], "zh-CN", "test-release")
        self.assertIn(b"&lt;tag&gt; &amp;", tmx)
        root = ET.fromstring(tmx)
        self.assertEqual(root.attrib["version"], "1.4")
        self.assertEqual(root.find("header").attrib["srclang"], "en-US")
        variants = root.findall("body/tu/tuv")
        self.assertEqual([v.attrib[reference.XML_LANG] for v in variants], ["en-US", "zh-CN"])
        self.assertEqual([v.find("seg").text for v in variants], [source, target])

    def test_duplicate_english_with_identical_translation_is_deduplicated(self):
        pairs = reference.translation_pairs({"a": "Stone", "b": "Stone"},
                                            {"a": "石头", "b": "石头"})
        self.assertEqual(pairs, [("Stone", "石头")])

    def test_duplicate_english_with_different_translations_keeps_both_entries(self):
        pairs = reference.translation_pairs({"a": "Back", "b": "Back", "c": "Back"},
                                            {"a": "返回", "b": "背面", "c": "返回"})
        root = ET.fromstring(reference.build_tmx(pairs, "zh-TW", "test-release"))
        self.assertEqual(len(root.findall("body/tu")), 2)
        self.assertEqual({tu.findall("tuv/seg")[1].text for tu in root.findall("body/tu")},
                         {"返回", "背面"})

    def test_missing_or_empty_segments_are_skipped_without_normalizing_text(self):
        source = {"a": "Missing", "b": "Empty", "c": "", "d": " Stone ", "e": "Stone"}
        target = {"b": "", "c": "空", "d": " 石头 ", "e": "石头", "extra": "无英文"}
        self.assertEqual(reference.translation_pairs(source, target),
                         [(" Stone ", " 石头 "), ("Stone", "石头")])

    def test_output_is_deterministic(self):
        source = {"b": "Stone", "a": "Back"}
        target = {"b": "石头", "a": "返回"}
        first = reference.translation_pairs(source, target)
        second = reference.translation_pairs(dict(reversed(list(source.items()))), target)
        self.assertEqual(reference.build_tmx(first, "zh-CN", "test-release"),
                         reference.build_tmx(list(reversed(second)), "zh-CN", "test-release"))

    def test_official_release_download_path_and_missing_target_resource(self):
        client = BytesIO()
        with ZipFile(client, "w") as archive:
            archive.writestr("assets/minecraft/lang/en_us.json", '{"key": "Stone"}')
        resources = {}

        def add_resource(url, data):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            resources[url] = data
            return {"url": url, "sha1": hashlib.sha1(data).hexdigest()}

        objects = {}
        for locale, translation in (("zh_cn", "石头"), ("zh_tw", "石頭")):
            data = json.dumps({"key": translation}).encode()
            digest = hashlib.sha1(data).hexdigest()
            add_resource(f"{reference.ASSET_BASE_URL}/{digest[:2]}/{digest}", data)
            objects[f"minecraft/lang/{locale}.json"] = {"hash": digest}
        index_info = add_resource("https://example.test/index", {"objects": objects})
        client_info = add_resource("https://example.test/client", client.getvalue())
        release = add_resource("https://example.test/release", {
            "assetIndex": index_info, "downloads": {"client": client_info}
        })
        release.update(id="test-release", type="release")
        add_resource(reference.VERSION_MANIFEST_URL, {
            "latest": {"release": "test-release", "snapshot": "test-snapshot"},
            "versions": [dict(release, id="test-snapshot", type="snapshot"), release],
        })

        def fake_download(session, url, sha1=None):
            data = resources[url]
            if sha1 is not None:
                self.assertEqual(hashlib.sha1(data).hexdigest(), sha1)
            return data

        with patch.object(reference, "download", side_effect=fake_download):
            version, languages = reference.fetch_languages()
            self.assertEqual(version, "test-release")
            self.assertEqual(languages, {"en_us": {"key": "Stone"},
                                        "zh_cn": {"key": "石头"}, "zh_tw": {"key": "石頭"}})
            self.assertEqual(reference.fetch_languages("test-release"), (version, languages))
            with self.assertRaisesRegex(ValueError, "Not an official"):
                reference.fetch_languages("test-snapshot")

            del objects["minecraft/lang/zh_tw.json"]
            index_info.update(add_resource(index_info["url"], {"objects": objects}))
            release.update(add_resource(release["url"], {
                "assetIndex": index_info, "downloads": {"client": client_info}
            }))
            add_resource(reference.VERSION_MANIFEST_URL, {
                "latest": {"release": "test-release"}, "versions": [release]
            })
            with self.assertRaisesRegex(ValueError, "Missing target language.*zh_tw"):
                reference.fetch_languages()

    def test_download_rejects_hash_mismatch(self):
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.content = b"test"
        self.assertEqual(reference.download(session, "https://example.test",
                                           hashlib.sha1(b"test").hexdigest()), b"test")
        with self.assertRaisesRegex(ValueError, "SHA-1 mismatch"):
            reference.download(session, "https://example.test", "0" * 40)

    def test_generation_keeps_targets_separate_and_does_not_publish_empty_target(self):
        languages = {"en_us": {"key": "Stone"}, "zh_cn": {"key": "石头"},
                     "zh_tw": {"key": "石頭"}}
        with TemporaryDirectory() as directory, \
                patch.object(reference, "fetch_languages", return_value=("test-release", languages)), \
                patch("builtins.print"):
            output = Path(directory)
            reference.generate_reference(output)
            for locale, language in reference.TARGET_LANGUAGES.items():
                path = output / f"java-en-{locale}.tmx"
                root = ET.fromstring(path.read_bytes())
                self.assertEqual(root.findall("body/tu/tuv")[1].attrib[reference.XML_LANG], language)
                self.assertEqual(root.findall("body/tu/tuv/seg")[1].text, languages[locale]["key"])
            old_outputs = {p.name: p.read_bytes() for p in output.iterdir()}
            languages["zh_tw"] = {"other": "无英文"}
            with self.assertRaisesRegex(ValueError, "No translated segments for zh_tw"):
                reference.generate_reference(output)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, old_outputs)


if __name__ == "__main__":
    unittest.main()
