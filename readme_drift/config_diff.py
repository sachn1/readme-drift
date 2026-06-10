"""Key-path diffing for configuration files (JSON, TOML, YAML)."""

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
import yaml  # type: ignore[import-untyped]
from .models import ChangeType, SymbolChange


@runtime_checkable
class KeyExtractor(Protocol):
    """Extract a flat key-path mapping from a config file's text content.

    Implement this protocol to add support for a new file type — no other
    module needs to change.
    """

    def extract(self, content: str) -> dict[str, str]:
        """Return {dot-notation-key-path: string-value} for all leaf nodes."""
        ...


def _flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    """Recursively flatten a nested structure into dot-notation key paths."""
    result: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else str(k)
            result.update(_flatten(v, new_key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            result.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        result[prefix] = str(obj)
    return result


def _all_segments(key_path: str) -> set[str]:
    """All meaningful name segments from a dot-notation path, no array indices."""
    parts = re.split(r"[.\[]", key_path)
    return {
        p.rstrip("]") for p in parts if p.rstrip("]") and not p.rstrip("]").isdigit()
    }


class JsonExtractor:
    def extract(self, content: str) -> dict[str, str]:
        """Parse JSON and return flat key-path → value dict."""
        if not content.strip():
            return {}
        try:
            return _flatten(json.loads(content))
        except json.JSONDecodeError:
            return {}


class TomlExtractor:
    def extract(self, content: str) -> dict[str, str]:
        """Parse TOML and return flat key-path → value dict."""
        if not content.strip():
            return {}
        try:
            return _flatten(tomllib.loads(content))
        except Exception:
            return {}


class YamlExtractor:
    def extract(self, content: str) -> dict[str, str]:
        """Parse YAML and return flat key-path → value dict."""
        if not content.strip():
            return {}
        try:
            data = yaml.safe_load(content)
        except Exception:
            return {}
        return _flatten(data) if data is not None else {}


_EXTRACTORS: dict[str, KeyExtractor] = {
    ".json": JsonExtractor(),
    ".toml": TomlExtractor(),
    ".yaml": YamlExtractor(),
    ".yml": YamlExtractor(),
}

CONFIG_SUFFIXES: frozenset[str] = frozenset(_EXTRACTORS)


def diff_config(
    old_source: str,
    new_source: str,
    file: str = "",
) -> list[SymbolChange]:
    """Compare two versions of a config file and return key changes.

    Parameters
    ----------
    old_source:
        Text content of the old version of the file.
    new_source:
        Text content of the new version of the file.
    file:
        Path of the file (used to select the right extractor and for reporting).

    Returns
    -------
    list[SymbolChange]
        Changes detected; leaf key names are used as symbol names so they
        match natural README references (e.g. ``build`` in ``npm run build``).
    """
    extractor = _EXTRACTORS.get(Path(file).suffix.lower() if file else "")
    if extractor is None:
        return []

    old_keys = extractor.extract(old_source)
    new_keys = extractor.extract(new_source)

    return _diff_key_paths(old_keys, new_keys, file)


def _diff_key_paths(
    old: dict[str, str],
    new: dict[str, str],
    file: str,
) -> list[SymbolChange]:
    """Diff two key-path dicts and emit SymbolChange entries.

    Only REMOVED and ADDED changes are emitted.  Rename detection for config
    keys is deferred — the same-value heuristic is too ambiguous when multiple
    keys share a value (e.g. several jobs using ``runs-on: ubuntu-latest``).

    All path segments (not just the leaf) are inspected so that an intermediate
    key like ``black`` in ``tool.black.line-length`` is correctly detected as
    removed even though ``line-length`` survives in ``tool.ruff.line-length``.
    Segments are cross-referenced against the *full* opposite dict so that
    structural keys (``jobs``, ``scripts``, ``tool``) that still exist in the
    other version are not spuriously reported.
    """
    changes: list[SymbolChange] = []

    removed_paths = set(old) - set(new)
    added_paths = set(new) - set(old)

    # Collect all name segments from the changed paths on each side.
    removed_segs: set[str] = set()
    for path in removed_paths:
        removed_segs.update(_all_segments(path))

    added_segs: set[str] = set()
    for path in added_paths:
        added_segs.update(_all_segments(path))

    # Cross-reference against ALL keys in the opposite dict so that shared
    # structural segments (e.g. "tool", "jobs") are not reported as removed.
    all_new_segs: set[str] = set()
    for path in new:
        all_new_segs.update(_all_segments(path))

    all_old_segs: set[str] = set()
    for path in old:
        all_old_segs.update(_all_segments(path))

    # Build reverse maps: segment → all full paths that contained it (for
    # key-path matching in README, e.g. "scripts.build" as well as "build").
    removed_seg_to_paths: dict[str, list[str]] = {}
    for path in removed_paths:
        for seg in _all_segments(path):
            removed_seg_to_paths.setdefault(seg, []).append(path)

    added_seg_to_paths: dict[str, list[str]] = {}
    for path in added_paths:
        for seg in _all_segments(path):
            added_seg_to_paths.setdefault(seg, []).append(path)

    for name in removed_segs - all_new_segs:
        changes.append(
            SymbolChange(
                name,
                ChangeType.REMOVED,
                file=file,
                key_paths=removed_seg_to_paths.get(name, []),
            )
        )

    for name in added_segs - all_old_segs:
        changes.append(
            SymbolChange(
                name,
                ChangeType.ADDED,
                file=file,
                key_paths=added_seg_to_paths.get(name, []),
            )
        )

    return changes
