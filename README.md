# Minecraft Bedrock Chinese Patch

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE) [![Update language files](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions/workflows/update.yml/badge.svg)](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions/workflows/update.yml) [![Crowdin](https://badges.crowdin.net/mcbe-chinese-patch/localized.svg)](https://crowdin.com/project/mcbe-chinese-patch)

This project aims to provide high-quality Chinese localization for Minecraft: Bedrock Edition. We strive to align the Bedrock Edition translations with the Java Edition as much as possible, while keeping modifications to the original text minimal.

## Project Background

The Bedrock Edition's translations often fall short of the Java Edition's community-driven quality on Crowdin. This is because a separate translation team, contracted by Microsoft, handles Bedrock's localization. Consequently, the Bedrock Edition suffers from inconsistent and inaccurate translations.

Despite years of player feedback and bug reports, the translation process for Bedrock Edition remains largely unchanged, and many issues persist. Even with the recent addition of contextual explanations from Microsoft, the contracted translators often seem unresponsive, over-relying on unreviewed machine translation. While they occasionally consult the Java Edition for corrections, new content translations are frequently riddled with errors.

Worse still, the Bedrock Edition sometimes suffers from translation "regressions", where previously correct text is inexplicably replaced with flawed machine translations after an update. This further degrades the already poor translation quality in the Bedrock Edition.

## Installation and Usage

**You can find the latest builds of this resource pack on the [Actions page](https://github.com/SkyEye-FAST/mcbe-chinese-patch/actions).**

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

- [Python 3.12+](https://www.python.org/)
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

### Manual Build Process

To build the resource packs from the source files, you only need to run the `pack.py` script:

``` bash
python scripts/pack.py
```

This will generate the `.mcpack` and `.zip` files in the `packed/` directory.

### Workflow Automation

This project uses GitHub Actions to automate the translation and packaging process. It runs every 2 hours to update language files, and the final resource packs (`.mcpack` and `.zip`) are generated and available for download.

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
