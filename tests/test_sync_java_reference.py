"""Offline contracts for replacing only the standalone Java reference TM."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sync_java_reference as sync


def response(data=None, status=200):
    """Create a mock Crowdin response with the requested payload and status."""
    result = MagicMock()
    result.status_code = status
    result.json.return_value = {"data": data}
    return result


class JavaReferenceSyncTests(unittest.TestCase):
    """Verify reference synchronization using local fixtures and a mock API."""

    def setUp(self):
        """Isolate generated files, credentials, API calls, and command output."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output_dir = Path(directory.name)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))
        self.enterContext(
            patch.dict(
                os.environ, {"CROWDIN_PERSONAL_TOKEN": "test-token", "CROWDIN_PROJECT_ID": "10"}
            )
        )
        self.generate = self.enterContext(
            patch.object(
                sync.java_reference, "generate_reference", side_effect=self.generate_fixture
            )
        )
        self.session = MagicMock()
        self.session_factory = self.enterContext(patch.object(sync.requests, "Session"))
        self.session_factory.return_value.__enter__.return_value = self.session
        self.enterContext(patch.object(sync.time, "sleep"))

    def generate_fixture(self, output_dir):
        """Generate valid TMX fixtures for both Chinese language variants."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for locale, language in sync.java_reference.TARGET_LANGUAGES.items():
            translations = ["石头", "石块"] if locale == "zh_cn" else ["石頭", "石塊"]
            data = sync.java_reference.build_tmx(
                [("Stone", text) for text in translations], language, "test-release"
            )
            (output_dir / f"java-en-{locale}.tmx").write_bytes(data)

    def lookup_responses(self, tms=None, default_tm_id=10):
        """Return project and translation memory lookup responses."""
        if tms is None:
            tms = [{"id": 20, "name": sync.TM_NAME, "defaultProjectIds": []}]
        return [response({"defaultTmId": default_tm_id}), response([{"data": tm} for tm in tms])]

    def apply_responses(self, final_status="finished"):
        """Return responses for clearing, uploading, and importing both targets."""
        return self.lookup_responses() + [
            response(status=204),
            response({"id": 101}, 201),
            response({"identifier": "cn-import", "status": "created"}, 202),
            response({"identifier": "cn-import", "status": "in_progress"}),
            response({"identifier": "cn-import", "status": "finished"}),
            response({"id": 102}, 201),
            response({"identifier": "tw-import", "status": "created"}, 202),
            response(
                {
                    "identifier": "tw-import",
                    "status": final_status,
                    "error": "fixture import error" if final_status == "failed" else None,
                }
            ),
            response({"id": 103}, 201),
            response({"identifier": "hk-import", "status": "finished"}, 202),
        ]

    def run_command(self, apply=False):
        """Run the synchronization command against the isolated output directory."""
        args = ["--output-dir", str(self.output_dir)]
        if apply:
            args.append("--apply")
        return sync.main(args)

    def calls(self):
        """Return recorded API methods and paths without the base URL."""
        return [
            (call.args[0], call.args[1].removeprefix(sync.API_URL))
            for call in self.session.request.call_args_list
        ]

    def test_dry_run_generates_and_validates_both_files_but_only_reads_crowdin(self):
        """Generate and validate both targets while keeping dry-run API calls read-only."""
        self.session.request.side_effect = self.lookup_responses()
        self.assertEqual(self.run_command(), 0)
        self.generate.assert_called_once_with(self.output_dir)
        self.assertEqual(self.calls(), [("GET", "/projects/10"), ("GET", "/tms")])
        self.assertIn("zh_CN entries: 2", self.stdout.getvalue())
        self.assertIn("zh_TW entries: 2", self.stdout.getvalue())
        self.assertIn("zh_HK entries: 2", self.stdout.getvalue())
        self.assertIn("Crowdin TM cleared: no (dry-run)", self.stdout.getvalue())
        self.assertNotIn("Sync successful", self.stdout.getvalue())

    def test_missing_tm_fails_without_remote_modification(self):
        """Reject a missing translation memory before changing remote data."""
        self.session.request.side_effect = self.lookup_responses(tms=[])
        self.assertEqual(self.run_command(apply=True), 1)
        self.assertIn("create it in Crowdin first", self.stderr.getvalue())
        self.assertTrue(all(method == "GET" for method, path in self.calls()))

    def test_generation_failure_never_contacts_crowdin(self):
        """Stop before opening an API session when reference generation fails."""
        self.generate.side_effect = ValueError("upstream unavailable")
        self.assertEqual(self.run_command(apply=True), 1)
        self.session_factory.assert_not_called()
        self.assertIn("upstream unavailable", self.stderr.getvalue())

    def test_invalid_second_tmx_never_contacts_crowdin(self):
        """Validate both TMX files before contacting Crowdin."""

        def invalid_fixture(output_dir):
            self.generate_fixture(output_dir)
            path = output_dir / "java-en-zh_tw.tmx"
            path.write_bytes(path.read_bytes().replace(b"zh-TW", b"zh-CN"))

        self.generate.side_effect = invalid_fixture
        self.assertEqual(self.run_command(apply=True), 1)
        self.session_factory.assert_not_called()
        self.assertIn("Invalid or empty TMX segment for zh-TW", self.stderr.getvalue())

    def test_clear_upload_import_wait_sequence_and_success_only_after_both_finish(self):
        """Follow the required API sequence and await both imports before success."""
        responses = self.apply_responses()

        def http_response(*args, **kwargs):
            self.assertNotIn("Sync successful", self.stdout.getvalue())
            return responses.pop(0)

        self.session.request.side_effect = http_response
        self.assertEqual(self.run_command(apply=True), 0)
        self.assertEqual(responses, [])
        self.assertEqual(
            self.calls(),
            [
                ("GET", "/projects/10"),
                ("GET", "/tms"),
                ("DELETE", "/tms/20/segments"),
                ("POST", "/storages"),
                ("POST", "/tms/20/imports"),
                ("GET", "/tms/20/imports/cn-import"),
                ("GET", "/tms/20/imports/cn-import"),
                ("POST", "/storages"),
                ("POST", "/tms/20/imports"),
                ("GET", "/tms/20/imports/tw-import"),
                ("POST", "/storages"),
                ("POST", "/tms/20/imports"),
            ],
        )
        calls = self.session.request.call_args_list
        for index, locale in ((3, "zh_cn"), (7, "zh_tw"), (10, "zh_hk")):
            upload = calls[index].kwargs
            self.assertEqual(
                upload["data"], (self.output_dir / f"java-en-{locale}.tmx").read_bytes()
            )
            self.assertEqual(upload["headers"]["Content-Type"], "application/octet-stream")
            self.assertEqual(upload["headers"]["Crowdin-API-FileName"], f"java-en-{locale}.tmx")
        self.assertEqual(calls[4].kwargs["json"], {"storageId": 101})
        self.assertEqual(calls[8].kwargs["json"], {"storageId": 102})
        self.assertEqual(calls[11].kwargs["json"], {"storageId": 103})
        self.assertIn("Crowdin TM cleared: yes", self.stdout.getvalue())
        self.assertIn("zh_CN import: finished", self.stdout.getvalue())
        self.assertIn("zh_TW import: finished", self.stdout.getvalue())
        self.assertIn("zh_HK import: finished", self.stdout.getvalue())
        self.assertIn("Sync successful: all language imports finished.", self.stdout.getvalue())

    def test_second_import_failure_reports_partial_update_and_recovery(self):
        """Report partial synchronization and recovery details after the second failure."""
        self.session.request.side_effect = self.apply_responses(final_status="failed")
        self.assertEqual(self.run_command(apply=True), 1)
        self.assertNotIn("Sync successful", self.stdout.getvalue())
        self.assertIn("zh_CN import: finished", self.stdout.getvalue())
        self.assertIn("zh_TW import: failed or unconfirmed", self.stdout.getvalue())
        self.assertIn("fixture import error", self.stderr.getvalue())
        self.assertIn("Recovery TM", self.stderr.getvalue())
        self.assertIn("java-en-zh_cn.tmx", self.stderr.getvalue())
        self.assertIn("java-en-zh_tw.tmx", self.stderr.getvalue())
        self.assertIn("/tms/20/imports/tw-import", self.stderr.getvalue())

    def test_first_import_timeout_does_not_start_second_import(self):
        """Stop after the first import times out and identify its pending state."""
        self.session.request.side_effect = self.apply_responses()
        with patch.object(sync, "IMPORT_TIMEOUT", 0):
            self.assertEqual(self.run_command(apply=True), 1)
        self.assertEqual(self.calls()[-1], ("POST", "/tms/20/imports"))
        self.assertEqual(len(self.calls()), 5)
        self.assertIn("zh_TW import: not started", self.stdout.getvalue())
        self.assertIn("timed out", self.stderr.getvalue())
        self.assertIn("Check pending imports", self.stderr.getvalue())

    def test_unlisted_pending_state_is_polled_until_finished(self):
        """Continue polling an unfamiliar pending status until import completion."""
        responses = self.apply_responses()
        responses[5] = response({"identifier": "cn-import", "status": "pending"})
        self.session.request.side_effect = responses
        self.assertEqual(self.run_command(apply=True), 0)
        self.assertIn("Sync successful", self.stdout.getvalue())

    def test_finished_response_with_error_details_is_not_reported_as_success(self):
        """Treat error details as failure even when the API reports a finished status."""
        responses = self.apply_responses()
        responses[-1] = response(
            {"identifier": "hk-import", "status": "finished", "error": "fixture incomplete import"},
            202,
        )
        self.session.request.side_effect = responses
        self.assertEqual(self.run_command(apply=True), 1)
        self.assertNotIn("Sync successful", self.stdout.getvalue())
        self.assertIn("fixture incomplete import", self.stderr.getvalue())

    def test_default_tm_and_ambiguous_name_are_rejected(self):
        """Reject default or ambiguously named memories before remote modification."""
        for tms in (
            [{"id": 10, "name": sync.TM_NAME, "defaultProjectIds": []}],
            [{"id": 20, "name": sync.TM_NAME, "defaultProjectIds": [99]}],
            [
                {"id": 20, "name": sync.TM_NAME, "defaultProjectIds": []},
                {"id": 21, "name": sync.TM_NAME, "defaultProjectIds": []},
            ],
        ):
            with self.subTest(tms=tms):
                self.session.request.reset_mock()
                self.session.request.side_effect = self.lookup_responses(tms=tms)
                self.assertEqual(self.run_command(apply=True), 1)
                self.assertTrue(all(method == "GET" for method, path in self.calls()))

    def test_clear_network_failure_is_unconfirmed_and_has_recovery_information(self):
        """Report an unknown clear result and recovery details after a network failure."""
        self.session.request.side_effect = self.lookup_responses() + [requests.Timeout("offline")]
        self.assertEqual(self.run_command(apply=True), 1)
        self.assertEqual(self.calls()[-1], ("DELETE", "/tms/20/segments"))
        self.assertIn("Crowdin TM cleared: unknown", self.stdout.getvalue())
        self.assertNotIn("Sync successful", self.stdout.getvalue())
        self.assertIn("Recovery TM", self.stderr.getvalue())

    def test_missing_credentials_fail_without_generation(self):
        """Reject missing credentials before generating files or contacting the API."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.run_command(), 1)
        self.generate.assert_not_called()
        self.session_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
