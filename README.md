# Minecraft Bedrock Chinese Patch

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE) [![Update language files](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions/workflows/update.yml/badge.svg)](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions/workflows/update.yml) [![Crowdin](https://badges.crowdin.net/mcbe-chinese-patch/localized.svg)](https://crowdin.com/project/mcbe-chinese-patch)

This project aims to provide high-quality Chinese localization for Minecraft: Bedrock Edition. We strive to align the Bedrock Edition translations with the Java Edition as much as possible, while keeping modifications to the original text minimal.

## Project Background

The Bedrock Edition's translations often fall short of the Java Edition's community-driven quality on Crowdin. This is because a separate translation team, contracted by Microsoft, handles Bedrock's localization. Consequently, the Bedrock Edition suffers from inconsistent and inaccurate translations.

Despite years of player feedback and bug reports, the translation process for Bedrock Edition remains largely unchanged, and many issues persist. Even with the recent addition of contextual explanations from Microsoft, the contracted translators often seem unresponsive, over-relying on unreviewed machine translation. While they occasionally consult the Java Edition for corrections, new content translations are frequently riddled with errors.

Worse still, the Bedrock Edition sometimes suffers from translation "regressions", where previously correct text is inexplicably replaced with flawed machine translations after an update. This further degrades the already poor translation quality in the Bedrock Edition.

## Installation and Usage

**You can find the latest builds of this resource pack on the [Actions page](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions).**

The game installation packages used by this project are sourced from [mcappx.com](https://www.mcappx.com/).

For instructions on how to install the resource pack, please refer to [Microsoft Learn](https://learn.microsoft.com/en-us/minecraft/creator/documents/gettingstarted).

> [!NOTE]
> Once the translation completion reaches a sufficient level, we will regularly release it on the [Releases page](https://github.com/SkyEye-FAST/mcbe-chinese-patch/releases).

## Contributing

We welcome contributions from the community! Here's how you can help:

- **Contribute Translations:** Join our [Crowdin project](https://crowdin.com/project/mcbe-chinese-patch) to contribute translations directly.
- **Report Code Issues:** For code-related issues, please submit an issue on our [GitHub repository](https://github.com/SkyEye-FAST/mcbe-chinese-patch/issues).
- **Submit Pull Requests:** If you have code improvements or fixes, feel free to submit a pull request.

> [!IMPORTANT]
> **Only code-related issues should be reported on GitHub.** For translation issues, please use Crowdin.

## File Structure

Here's a breakdown of the repository's file structure:

- `extracted/`: Contains the raw language files as extracted directly from the game.
- `merged/`: Holds consolidated language files, organized by game version.
- `patched/`: This directory contains the final, ready-to-use language files with the applied patches from Crowdin.
- `sources/`: Stores the generated TSV source files for use with Crowdin.
- `packed/`: Contains the final `.mcpack` and `.zip` resource packs.
- `resources/`: Includes supplementary resources such as the pack manifest and language metadata.
- `scripts/`: Houses utility scripts for managing and updating the translations.
- `.github/workflows/`: Contains the GitHub Actions workflow for automating the translation process.

## For Developers

If you want to contribute to the development of this project, here's how to get started.

### Prerequisites

- [Python 3.11+](https://www.python.org/)
- [.NET 9.0](https://dotnet.microsoft.com/en-us/download/dotnet/9.0)
- [uv](https://github.com/astral-sh/uv)

### Setup

1. **Clone the repository:**

    ``` bash
    git clone https://github.com/SkyEye-FAST/mcbe-chinese-patch.git
    cd mcbe-chinese-patch
    ```

2. **Create a virtual environment and install dependencies:**

    ``` bash
    uv venv
    uv sync
    ```

    This will create a virtual environment in the `.venv` directory and install the required packages listed in `pyproject.toml`.

3. **Activate the virtual environment:**

    - **Windows (PowerShell):**

        ``` powershell
        .venv\Scripts\Activate.ps1
        ```

    - **macOS/Linux:**

        ``` bash
        source .venv/bin/activate
        ```

### Manual Build

To build the resource packs from the source files, you only need to run the `pack.py` script:

``` bash
python scripts/pack.py
```

This will generate the `.mcpack` and `.zip` files in the `packed/` directory.

The build requires `versions.json`, the current `sources/<branch>/en_US.tsv`,
and Crowdin TSV files in `patched/<branch>/` for every locale listed in
`resources/texts/languages.json`, for Release, Beta, and Preview. Only nonempty
translations whose keys still exist in the current source are included. Missing
inputs or invalid TSV headers fail the build instead of reusing old `.lang` files.

Run the small offline contract suite with no additional test dependencies:

``` bash
uv run python -m unittest discover -s tests -v
```

### Java Edition Reference Translation Memory

Generate all three reference TMs with one command:

``` bash
uv run python scripts/java_reference.py
```

The script reads Mojang's [official version manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json)
and selects `latest.release`, never a snapshot. It gets `en_us.json` from the
official client JAR and `zh_cn.json` / `zh_tw.json` / `zh_hk.json` from the release's asset index
and Mojang's asset server. Downloads are checked against Mojang's SHA-1 hashes.
Raw resources are read in memory and are not saved or committed.

The ignored `java-reference/` directory contains `java-en-zh_cn.tmx`,
`java-en-zh_tw.tmx`, and `java-en-zh_hk.tmx`. To reproduce a particular release or choose another output
directory, run:

``` bash
uv run python scripts/java_reference.py --version 26.3 --output-dir java-reference
```

Each Java English string is a complete TM segment. Java keys only pair strings
within the Java resources; no Java/Bedrock key alignment or fuzzy matching is
performed. Identical English/Chinese pairs collapse into one entry, while
different Chinese translations of the same English remain separate entries.
Missing or empty segments are skipped and counted; missing language files or
targets with no translated segments fail generation. Text, whitespace, and
placeholders are preserved. Entries sort by exact English text and then Chinese
text, with no timestamps; the same release resources produce identical TMX bytes.
`zh_CN`, `zh_TW`, and `zh_HK` remain separate targets, represented by standard
`zh-CN`, `zh-TW`, and `zh-HK` TMX language tags; there is no script conversion.

To use these files in Crowdin, follow the [Translation Memory documentation](https://support.crowdin.com/translation-memory/):

1. From the project owner's profile, open **TM > Create TM**, name it
   **Minecraft Java Edition Reference**, select English as the default display
   language, and assign it to this project.
2. Open that TM's **View Records > Upload** and upload all three generated TMX files.
   Check the English, Simplified Chinese, Taiwan Traditional Chinese, and Hong Kong
   Traditional Chinese segments and that alternative translations remain available.
3. Keep the project's existing default TM. This additional TM is for reference
   suggestions only; do not enable automatic translation or apply it through
   auto-translation. Use the manual sync below for updates; importing without
   clearing retains old alternatives and is not a full replacement.

This command does not access Crowdin, modify `sources/*.tsv` Context or the
source/translation file layout, or participate in resource pack builds. It does
not change any translation or invoke AI inference.

#### Manual Crowdin TM Sync

Set the existing `CROWDIN_PERSONAL_TOKEN` and `CROWDIN_PROJECT_ID` environment
variables. The token needs access to this project, read access to project settings,
and TM read/write and storage upload permissions. Do not commit credentials or TM
IDs. Create the separate **Minecraft Java Edition Reference** TM first.

``` bash
# Default dry-run: generate/validate all TMX files, find the TM, and show counts.
uv run python scripts/sync_java_reference.py

# Explicitly clear the reference TM and import all current-release TMX files.
uv run python scripts/sync_java_reference.py --apply
```

The command uses [Crowdin API v2](https://support.crowdin.com/developer/api/v2/),
matches the TM name exactly, and rejects duplicate names or any project default
TM. All complete files are validated before any remote modification. `--apply`
fully replaces the reference TM: clear, upload/import Simplified Chinese and wait
for completion, then upload/import Taiwan and Hong Kong Traditional Chinese and wait. Only all
finished imports count as success. Run one sync at a time.

Failures exit nonzero. A failure after a clear request may leave the TM empty or
partial; the command reports import IDs/status URLs and the validated local TMX
paths for recovery. Check outstanding imports before retrying; saved files can
be restored manually, or `--apply` can regenerate the latest release and replace
the TM again. There is no automatic rollback or retained historical TM. This
remains a manual command; GitHub Actions, project translations, Context, resource
pack builds, and AI configuration are unchanged. Verify an actual Crowdin import
before considering CI automation.

### Workflow

This project uses GitHub Actions to automate the translation, Crowdin synchronization, and packaging process. It runs every 2 hours to update language files and synchronize translations with Crowdin. The final resource packs (`.mcpack` and `.zip`) are then generated and available for download.

Each run first checks upstream Release and Development versions with
`uv run scripts/extract.py --check`. Package downloads and extraction run only
when a version changes or the existing extraction fails validation. Crowdin
synchronization and packaging still run when game versions are unchanged.
Workflow concurrency serializes runs that write to `main`.

`uv run scripts/extract.py` performs a full extraction. Each retry fetches both
versions, downloads packages, and extracts into a fresh temporary directory.
Both targets must contain nonempty base language files and matching JSON before
the complete directories replace the previous extraction. Directory replacements
use same-filesystem renames with rollback on errors; `versions.json` is atomically
updated last. Exhausted retries exit with a nonzero status. Merge, source
generation, packaging, and artifact upload also fail on missing required inputs.

#### Required GitHub Secrets

To run the automated workflow, the following secrets must be configured in your GitHub repository:

- `MINECRAFT_CIK_KEYS`: JSON object mapping CIK GUIDs to hex-encoded, complete 48-byte `.cik` files for both Release and Preview GDK packages
- `CROWDIN_PROJECT_ID`: Crowdin project ID
- `CROWDIN_PERSONAL_TOKEN`: Crowdin API token

On a Windows machine with licensed Minecraft Release and Preview installations,
run `uv run python scripts/extract_cik.py`. The script collects all Minecraft keys
from local licenses and writes the ignored `extracted/tools/minecraft-cik-keys.json`
without printing secret values. Upload that file with GitHub CLI:

``` bash
gh secret set MINECRAFT_CIK_KEYS < extracted/tools/minecraft-cik-keys.json
```

The former single-key secrets are no longer used. If a package reports a missing
CIK GUID, update and launch the corresponding installed game to refresh its license,
then extract and upload the current keys again. Missing or invalid keys stop
extraction immediately instead of downloading the same package five times;
previous language files and `versions.json` remain intact.

## License

This project is licensed under the [Apache 2.0 License](LICENSE).

``` text
    Copyright 2025 Minecraft Bedrock Chinese Patch Authors

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
```
