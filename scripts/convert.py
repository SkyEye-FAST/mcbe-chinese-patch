"""Minecraft: Bedrock Edition Language File Converter.

This module provides utilities for converting between .lang and .json formats
used in Minecraft Bedrock Edition language files.
"""

from collections import OrderedDict
from pathlib import Path
from typing import Any

import orjson


def convert_lang_to_json(lang_content: str) -> OrderedDict[str, str]:
    """Convert .lang file content to JSON-compatible ordered dictionary.

    Args:
        lang_content (str): Content of the .lang file as a string

    Returns:
        OrderedDict: JSON-compatible ordered dictionary representation of the lang file.

    The function parses Minecraft .lang files which use key=value format,
    ignoring empty lines and comments starting with ##.
    """
    json_data: OrderedDict[str, str] = OrderedDict()

    for line in lang_content.splitlines():
        line = line.strip(" \t\r\n\f\v")  # Keep U+00A0

        if not line or line.startswith("##"):
            continue

        equal_index = line.find("=")
        if equal_index > 0:
            key = line[:equal_index].strip()
            value = line[equal_index + 1 :].strip(" \t\r\n\f\v")

            if key not in json_data:
                json_data[key] = value

    return json_data


def convert_json_to_lang(json_data: dict[str, Any]) -> str:
    """Convert JSON data to .lang file content format.

    Args:
        json_data (dict): JSON data to convert

    Returns:
        str: .lang file content with key=value format
    """
    lines: list[str] = []

    for key, value in json_data.items():
        lines.append(f"{str(key)}={str(value)}")

    return "\n".join(lines)


def remove_duplicate_keys(lang_content: str) -> str:
    """Remove duplicate keys from lang file content, keeping first occurrence.

    Args:
        lang_content (str): Original lang file content as a string

    Returns:
        str: Cleaned lang file content without duplicate keys.
            Comments and empty lines are preserved as-is.
    """
    seen_keys: set[str] = set()
    result_lines: list[str] = []

    for line in lang_content.splitlines():
        trimmed_line = line.strip()

        if not trimmed_line or trimmed_line.startswith("##"):
            result_lines.append(line)
            continue

        equal_index = trimmed_line.find("=")
        if equal_index > 0:
            key = trimmed_line[:equal_index].strip()

            if key not in seen_keys:
                seen_keys.add(key)
                result_lines.append(line)
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def clean_lang_content(raw_content: str) -> str:
    """Clean and normalize language file content.

    Args:
        raw_content (str): Raw content from the language file

    Returns:
        str: Cleaned content with normalized line endings and no empty lines
    """
    cleaned_content = raw_content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")

    cleaned_content = "\n".join(
        line for line in cleaned_content.splitlines() if line.strip(" \t\r\n\f\v")
    )

    return remove_duplicate_keys(cleaned_content) if cleaned_content.strip() else ""


def load_lang_file(file_path: Path) -> OrderedDict[str, str]:
    """Load a .lang file and convert it to an ordered dictionary.

    Args:
        file_path (Path): Path to the .lang file

    Returns:
        OrderedDict: Parsed language data

    Raises:
        FileNotFoundError: If the file doesn't exist
        PermissionError: If the file cannot be read
    """
    content = file_path.read_text(encoding="utf-8")
    cleaned_content = clean_lang_content(content)
    return convert_lang_to_json(cleaned_content)


def save_lang_file(file_path: Path, data: dict[str, Any]) -> None:
    """Save data as a .lang file.

    Args:
        file_path (Path): Path where to save the .lang file
        data (dict): Data to save

    Raises:
        PermissionError: If the file cannot be written
    """
    lang_content = convert_json_to_lang(data)
    file_path.write_text(lang_content, encoding="utf-8", newline="\n")


def load_json_file(file_path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents.

    Args:
        file_path (Path): Path to the JSON file

    Returns:
        dict: Parsed JSON data

    Raises:
        FileNotFoundError: If the file doesn't exist
        orjson.JSONDecodeError: If the file contains invalid JSON
    """
    with file_path.open("r", encoding="utf-8") as f:
        return orjson.loads(f.read())


def save_json_file(file_path: Path, data: dict[str, Any], sort_keys: bool = True) -> None:
    """Save data as a JSON file with proper formatting.

    Args:
        file_path (Path): Path where to save the JSON file
        data (dict): Data to save
        sort_keys (bool): Whether to sort keys in the output

    Raises:
        PermissionError: If the file cannot be written
    """
    options = orjson.OPT_INDENT_2
    if sort_keys:
        options |= orjson.OPT_SORT_KEYS

    with file_path.open("wb") as f:
        f.write(orjson.dumps(data, option=options))


def convert_lang_to_json_file(lang_file: Path, json_file: Path | None = None) -> Path:
    """Convert a .lang file to a .json file.

    Args:
        lang_file (Path): Path to the source .lang file
        json_file (Path | None): Path for the output .json file.
                                 If None, uses the same name with .json extension

    Returns:
        Path: Path to the created JSON file

    Raises:
        FileNotFoundError: If the source file doesn't exist
        PermissionError: If files cannot be read or written
    """
    if json_file is None:
        json_file = lang_file.with_suffix(".json")

    data = load_lang_file(lang_file)
    save_json_file(json_file, data)
    return json_file


def convert_json_to_lang_file(json_file: Path, lang_file: Path | None = None) -> Path:
    """Convert a .json file to a .lang file.

    Args:
        json_file (Path): Path to the source .json file
        lang_file (Path | None): Path for the output .lang file.
                                 If None, uses the same name with .lang extension

    Returns:
        Path: Path to the created .lang file

    Raises:
        FileNotFoundError: If the source file doesn't exist
        PermissionError: If files cannot be read or written
        orjson.JSONDecodeError: If the JSON file is invalid
    """
    if lang_file is None:
        lang_file = json_file.with_suffix(".lang")

    data = load_json_file(json_file)
    save_lang_file(lang_file, data)
    return lang_file


def main() -> None:
    """Main entry point for the converter when run as a script."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python convert.py <input_file> [output_file]")
        print("Converts between .lang and .json formats based on input file extension")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not input_file.exists():
        print(f"Error: Input file '{input_file}' does not exist")
        sys.exit(1)

    try:
        if input_file.suffix.lower() == ".lang":
            result_file = convert_lang_to_json_file(input_file, output_file)
            print(f"Converted {input_file} to {result_file}")
        elif input_file.suffix.lower() == ".json":
            result_file = convert_json_to_lang_file(input_file, output_file)
            print(f"Converted {input_file} to {result_file}")
        else:
            print(f"Error: Unsupported file extension '{input_file.suffix}'")
            print("Supported extensions: .lang, .json")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
