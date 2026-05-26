"""Tests for checker logic — symbol-to-README matching."""

from pathlib import Path

import pytest

from readme_drift.drift_checker import _is_excluded, _symbols_from_changes
from readme_drift.models import ChangeType, ReadmeMatch, StalenessFinding, SymbolChange


def _readme_match(symbol: str) -> ReadmeMatch:
    return ReadmeMatch(
        symbol=symbol,
        line_number=5,
        line_text=f"Use `{symbol}` to do things.",
        matched_text=f"`{symbol}`",
        readme_path=Path("README.md"),
    )


def test_added_symbol_does_not_produce_finding():
    # ADDED symbols found in the README must never be flagged as stale —
    # a README that already documents a new symbol is correct, not stale.
    change = SymbolChange(name="new_func", change_type=ChangeType.ADDED)
    readme_matches = {"new_func": [_readme_match("new_func")]}

    findings: list[StalenessFinding] = []
    for c in [change]:
        if c.change_type == ChangeType.ADDED:
            continue
        if c.name in readme_matches:
            findings.append(
                StalenessFinding(change=c, readme_matches=readme_matches[c.name])
            )

    assert findings == []


def test_symbols_from_changes_deduplicates():
    changes = [
        SymbolChange(name="foo", change_type=ChangeType.REMOVED),
        SymbolChange(name="foo", change_type=ChangeType.SIGNATURE_CHANGED),
        SymbolChange(name="bar", change_type=ChangeType.REMOVED),
    ]
    symbols = _symbols_from_changes(changes)
    assert sorted(symbols) == ["bar", "foo"]


@pytest.mark.parametrize(
    "file_str, patterns, expected",
    [
        ("generated/models.py", ["generated/"], True),
        ("src/models.py", ["generated/"], False),
        ("src/models.py", ["*.py"], True),
        ("src/models.py", ["models.py"], True),
        ("src/models.py", ["other.py"], False),
        ("tests/conftest.py", ["tests/"], True),
        ("readme_drift/git.py", ["readme_drift/git.py"], True),
    ],
)
def test_is_excluded(file_str, patterns, expected):
    assert _is_excluded(Path(file_str), patterns) == expected


def test_is_excluded_empty_patterns():
    assert not _is_excluded(Path("src/models.py"), [])
