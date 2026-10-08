"""Validate the Minecraft CIK file collection shared by local extraction and CI."""

import uuid

import orjson


class CikError(ValueError):
    """A missing or invalid decryption key requires configuration changes."""


def validate_cik(guid: str, data: bytes) -> str:
    """Validate a 48-byte XvdTool CIK and return its canonical GUID."""
    try:
        identifier = uuid.UUID(guid)
    except (ValueError, AttributeError):
        raise CikError("CIK identifiers must be GUIDs") from None
    if len(data) != 48:
        raise CikError(f"CIK {identifier} must contain a complete 48-byte .cik file")
    if data[:16] != identifier.bytes_le:
        raise CikError(f"CIK {identifier} does not match its embedded GUID")
    return str(identifier)


def parse_cik_keys(value: str) -> dict[str, bytes]:
    """Decode MINECRAFT_CIK_KEYS without including secret values in errors."""
    try:
        entries = orjson.loads(value)
    except orjson.JSONDecodeError:
        raise CikError("MINECRAFT_CIK_KEYS must be a JSON object of GUIDs to hex CIK files") from None
    if not isinstance(entries, dict) or not entries:
        raise CikError("MINECRAFT_CIK_KEYS must contain at least one CIK")
    keys = {}
    for guid, encoded in entries.items():
        if not isinstance(encoded, str):
            raise CikError("MINECRAFT_CIK_KEYS values must be hex strings")
        try:
            data = bytes.fromhex(encoded)
        except ValueError:
            raise CikError("MINECRAFT_CIK_KEYS contains invalid hex") from None
        identifier = validate_cik(guid, data)
        if identifier in keys:
            raise CikError(f"Duplicate CIK GUID: {identifier}")
        keys[identifier] = data
    return keys
