"""Generate current Crowdin translations and package Release, Beta and Preview."""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from convert import extract_current_translations, save_lang_file

BRANCHES = ("release", "beta", "preview")


def create_pack_archive(
    branch: str, lang_files: list[Path], version: str, base_dir: Path
) -> None:
    """Build both archives from a fresh directory, including only current languages."""
    output_dir = base_dir / "packed"
    output_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{branch}-", dir=output_dir) as temporary:
        pack_dir = Path(temporary)
        shutil.copy2(base_dir / "resources/manifest.json", pack_dir / "manifest.json")
        texts_dir = pack_dir / "texts"
        texts_dir.mkdir()
        for lang_file in lang_files:
            shutil.copy2(lang_file, texts_dir / lang_file.name)
        for filename in ("languages.json", "language_names.json"):
            shutil.copy2(base_dir / "resources/texts" / filename, texts_dir / filename)

        base_name = f"MCBE_Chinese_Patch_{branch}_{version}"
        zip_path = output_dir / f"{base_name}.zip"
        staged_zip = pack_dir / "pack.zip"
        # Enumerate inputs before creating the archive, so it cannot include itself.
        files = sorted(path for path in pack_dir.rglob("*") if path.is_file())
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(pack_dir))
        staged_mcpack = pack_dir / "pack.mcpack"
        shutil.copy2(staged_zip, staged_mcpack)
        staged_zip.replace(zip_path)
        staged_mcpack.replace(output_dir / f"{base_name}.mcpack")
        print(f"Created {base_name}.zip (.mcpack)")


def main(base_dir: Path | None = None) -> None:
    """Require all channels and declared locales, then generate and pack them."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    versions = json.loads((base_dir / "versions.json").read_text(encoding="utf-8"))["versions"]
    languages = json.loads(
        (base_dir / "resources/texts/languages.json").read_text(encoding="utf-8")
    )
    if not languages:
        raise ValueError("No resource pack languages declared")

    for branch in BRANCHES:
        version = versions["release" if branch == "release" else "development"]
        if not isinstance(version, str) or not version:
            raise ValueError(f"Missing version for {branch}")
        branch_dir = base_dir / "patched" / branch
        source = base_dir / "sources" / branch / "en_US.tsv"
        lang_files = []
        for language in languages:
            tsv_file = branch_dir / f"{language}.tsv"
            translations = extract_current_translations(tsv_file, source)
            lang_file = tsv_file.with_suffix(".lang")
            save_lang_file(lang_file, translations)
            lang_files.append(lang_file)
        create_pack_archive(branch.capitalize(), lang_files, version, base_dir)


if __name__ == "__main__":
    main()
