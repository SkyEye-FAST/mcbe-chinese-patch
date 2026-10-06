"""Replace the standalone Crowdin Java Reference TM; dry-run unless --apply is set."""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import java_reference
import requests

API_URL = "https://api.crowdin.com/api/v2"
TM_NAME = "Minecraft Java Edition Reference"
IMPORT_TIMEOUT = 600
POLL_INTERVAL = 2


@dataclass(frozen=True)
class TMXDocument:
    """Keep a validated language TMX snapshot and its entry count for upload."""

    locale: str
    path: Path
    data: bytes
    entries: int


def validate_tmx(data: bytes, target_language: str) -> tuple[str, int]:
    """Parse every unit and verify the complete bilingual file before clearing a TM."""
    root = ET.fromstring(data)
    header = root.find("header")
    if root.tag != "tmx" or root.get("version") != "1.4" or header is None:
        raise ValueError("Invalid TMX root/header")
    required = ("creationtool", "creationtoolversion", "segtype", "o-tmf", "adminlang", "datatype")
    if header.get("srclang") != "en-US" or any(not header.get(key) for key in required):
        raise ValueError("Invalid TMX header attributes")
    version = header.findtext("prop[@type='x-java-version']")
    if not version:
        raise ValueError("Missing Java release in TMX")
    body = root.find("body")
    if body is None or not len(body):
        raise ValueError("Empty TMX body")
    pairs = []
    for unit in body:
        variants = list(unit)
        if unit.tag != "tu" or len(variants) != 2:
            raise ValueError("TMX unit must contain exactly two language variants")
        texts = []
        for variant, language in zip(variants, ("en-US", target_language)):
            segments = list(variant)
            if (
                variant.tag != "tuv"
                or variant.get(java_reference.XML_LANG) != language
                or len(segments) != 1
                or segments[0].tag != "seg"
                or len(segments[0])
                or not segments[0].text
            ):
                raise ValueError(f"Invalid or empty TMX segment for {language}")
            texts.append(segments[0].text)
        pairs.append(tuple(texts))
    if pairs != sorted(set(pairs)):
        raise ValueError("TMX entries must be unique pairs in deterministic order")
    return version, len(pairs)


def prepare_reference(output_dir: Path) -> tuple[str, list[TMXDocument]]:
    """Generate and validate both reference files from the latest official release."""
    # Always generate latest.release; a stale local file is never a fallback.
    java_reference.generate_reference(output_dir)
    documents = []
    versions = set()
    for locale, language in java_reference.TARGET_LANGUAGES.items():
        path = output_dir / f"java-en-{locale}.tmx"
        data = path.read_bytes()
        version, entries = validate_tmx(data, language)
        versions.add(version)
        documents.append(TMXDocument(locale[:2] + "_" + locale[3:].upper(), path, data, entries))
    if len(versions) != 1:
        raise ValueError("The two TMX files refer to different Java releases")
    return versions.pop(), documents


def api_request(
    session: requests.Session, method: str, path: str, expected_status: int = 200, **kwargs
) -> requests.Response:
    """Send a Crowdin API request and require the expected HTTP status."""
    response = session.request(method, API_URL + path, timeout=60, **kwargs)
    response.raise_for_status()
    if response.status_code != expected_status:
        raise RuntimeError(f"Crowdin {method} {path}: unexpected HTTP {response.status_code}")
    return response


def find_reference_tm(session: requests.Session, project_id: int) -> dict:
    """Find the unique reference TM by name and reject project default TMs."""
    project = api_request(session, "GET", f"/projects/{project_id}").json()["data"]
    if "defaultTmId" not in project:
        raise ValueError("Cannot verify the project's default TM")
    matches = []
    offset = 0
    while True:
        page = api_request(
            session,
            "GET",
            "/tms",
            params={
                "filter": TM_NAME,
                "limit": 500,
                "offset": offset,
            },
        ).json()["data"]
        matches.extend(item["data"] for item in page if item["data"]["name"] == TM_NAME)
        if len(page) < 500:
            break
        offset += len(page)
    if not matches:
        raise ValueError(f"TM '{TM_NAME}' not found; create it in Crowdin first")
    if len(matches) != 1:
        raise ValueError(f"Multiple TMs named '{TM_NAME}'; resolve the duplicate names first")
    tm = matches[0]
    if "defaultProjectIds" not in tm:
        raise ValueError("Cannot verify that the reference TM is separate from project default TMs")
    if tm["id"] == project["defaultTmId"] or tm["defaultProjectIds"]:
        raise ValueError("Refusing to replace a project default TM")
    return tm


def wait_for_import(session: requests.Session, tm_id: int, job: dict) -> None:
    """Poll an import until it finishes, reports an error, or reaches the deadline."""
    identifier = job["identifier"]
    deadline = time.monotonic() + IMPORT_TIMEOUT
    while True:
        status = job["status"]
        detail = job.get("error") or job.get("errors")
        if status == "failed" or detail:
            raise RuntimeError(
                f"Import {identifier}: {status}; {detail or 'no error details supplied'}"
            )
        if status == "finished":
            return
        # The API's status type is an open string; only 'finished' confirms success.
        # Other states remain unconfirmed and are polled until the bounded deadline.
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Import {identifier} timed out; last status: {status}")
        time.sleep(POLL_INTERVAL)
        job = api_request(session, "GET", f"/tms/{tm_id}/imports/{identifier}").json()["data"]


def print_status(cleared: str, imports: dict[str, str]) -> None:
    """Print the remote clear state and the import state of each target language."""
    print(f"Crowdin TM cleared: {cleared}")
    for locale, status in imports.items():
        print(f"{locale} import: {status}")


def sync_reference(output_dir: Path, project_id: int, token: str, apply: bool = False) -> None:
    """Preview the reference sync or explicitly replace the TM with both languages."""
    version, documents = prepare_reference(output_dir)
    with requests.Session() as session:
        session.headers.update({"Authorization": f"Bearer {token}"})
        tm = find_reference_tm(session, project_id)
        tm_id = tm["id"]
        print(f"Java Edition: {version}")
        print(f"TM: {TM_NAME}")
        for document in documents:
            print(f"{document.locale} entries: {document.entries}")
        imports = {document.locale: "not started" for document in documents}
        if not apply:
            print_status("no (dry-run)", imports)
            print("Dry-run complete; use --apply to replace this TM.")
            return

        cleared = "unknown (clear request did not complete)"
        jobs = {}
        active_locale = None
        try:
            api_request(session, "DELETE", f"/tms/{tm_id}/segments", expected_status=204)
            cleared = "yes"
            for document in documents:
                active_locale = document.locale
                imports[active_locale] = "uploading"
                storage = api_request(
                    session,
                    "POST",
                    "/storages",
                    expected_status=201,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Crowdin-API-FileName": document.path.name,
                    },
                    data=document.data,
                ).json()["data"]
                imports[active_locale] = "starting"
                job = api_request(
                    session,
                    "POST",
                    f"/tms/{tm_id}/imports",
                    expected_status=202,
                    json={"storageId": storage["id"]},
                ).json()["data"]
                jobs[active_locale] = job["identifier"]
                imports[active_locale] = "in progress"
                wait_for_import(session, tm_id, job)
                imports[active_locale] = "finished"
        except (Exception, KeyboardInterrupt):
            if active_locale is not None:
                imports[active_locale] = "failed or unconfirmed"
            print_status(cleared, imports)
            print("Sync failed; the remote TM may be empty or partially replaced.", file=sys.stderr)
            print(f"Recovery TM: {TM_NAME} (ID {tm_id})", file=sys.stderr)
            for document in documents:
                print(
                    f"Validated {document.locale} TMX: {document.path.resolve()}", file=sys.stderr
                )
            for locale, identifier in jobs.items():
                print(
                    f"Check {locale} import: {API_URL}/tms/{tm_id}/imports/{identifier}",
                    file=sys.stderr,
                )
            print(
                "Check pending imports in Crowdin before retrying. Restore both saved TMX files "
                "manually after clearing this reference TM, or rerun this command with --apply "
                "once no import is running. A retry generates the latest release and replaces "
                "the whole reference TM again; there is no automatic rollback.",
                file=sys.stderr,
            )
            raise
        print_status(cleared, imports)
        print("Sync successful: both language imports finished.")


def main(argv: list[str] | None = None) -> int:
    """Read CLI options and credentials, run the sync, and return an exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Clear and replace the reference TM")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=java_reference.DEFAULT_OUTPUT_DIR,
        help="Keep validated TMX files here (default: java-reference/)",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("CROWDIN_PERSONAL_TOKEN", "")
    project = os.environ.get("CROWDIN_PROJECT_ID", "")
    if not token or not project:
        print("Set CROWDIN_PERSONAL_TOKEN and CROWDIN_PROJECT_ID before syncing.", file=sys.stderr)
        return 1
    try:
        project_id = int(project)
        if project_id <= 0:
            raise ValueError("CROWDIN_PROJECT_ID must be a positive integer")
        sync_reference(args.output_dir, project_id, token, args.apply)
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error).replace(token, "[redacted]") if str(error) else "interrupted"
        print(f"Java Reference sync failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
