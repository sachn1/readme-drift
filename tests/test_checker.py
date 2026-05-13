"""Tests for checker logic — symbol-to-README matching."""

from pathlib import Path

from readme_check.checker import _primary_name, _symbols_from_changes
from readme_check.models import ChangeType, ReadmeMatch, StalenessFinding, SymbolChange


def _renamed(old: str, new: str) -> SymbolChange:
    return SymbolChange(
        name=new,
        change_type=ChangeType.RENAMED,
        old_signature=old,
    )


def _readme_match(symbol: str) -> ReadmeMatch:
    return ReadmeMatch(
        symbol=symbol,
        line_number=5,
        line_text=f"Use `{symbol}` to do things.",
        matched_text=f"`{symbol}`",
        readme_path=Path("README.md"),
    )


# --- _primary_name ---


def test_primary_name_returns_old_name_for_rename():
    change = _renamed("fuzzy_lookup", "fuzzy_lookup_now")
    assert _primary_name(change) == "fuzzy_lookup"


def test_primary_name_returns_new_name_for_other_changes():
    for change_type in (
        ChangeType.ADDED,
        ChangeType.REMOVED,
        ChangeType.SIGNATURE_CHANGED,
    ):
        change = SymbolChange(name="my_func", change_type=change_type)
        assert _primary_name(change) == "my_func"


# --- _symbols_from_changes ---


def test_symbols_from_changes_includes_old_name_for_rename():
    change = _renamed("fuzzy_lookup", "fuzzy_lookup_now")
    symbols = _symbols_from_changes([change])
    assert "fuzzy_lookup" in symbols
    assert "fuzzy_lookup_now" in symbols


# --- End-to-end: rename in code, old name still in README → should find a match ---


def test_rename_matches_readme_via_old_name():
    """
    Regression: renaming fuzzy_lookup → fuzzy_lookup_now while the README still
    references fuzzy_lookup must produce a finding. Previously _primary_name
    returned the new name, so the README match (stored under the old name) was
    never found.
    """
    change = _renamed("fuzzy_lookup", "fuzzy_lookup_now")
    readme_matches = {"fuzzy_lookup": [_readme_match("fuzzy_lookup")]}

    findings: list[StalenessFinding] = []
    relevant_name = _primary_name(change)
    if relevant_name in readme_matches:
        findings.append(
            StalenessFinding(
                change=change, readme_matches=readme_matches[relevant_name]
            )
        )

    assert len(findings) == 1
    assert findings[0].change.name == "fuzzy_lookup_now"
    assert findings[0].readme_matches[0].symbol == "fuzzy_lookup"
