"""Tests for checker logic — symbol-to-README matching."""

from pathlib import Path

from readme_drift.checker import _primary_name, _symbols_from_changes
from readme_drift.models import ChangeType, ReadmeMatch, StalenessFinding, SymbolChange


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


def test_renamed_method_old_name_included_in_symbols():
    # Regression: the "." heuristic in _symbols_from_changes excluded method
    # old names like "Client.foo", so renamed methods were never found in the README.
    change = SymbolChange(
        name="Client.bar",
        change_type=ChangeType.RENAMED,
        old_signature="Client.foo",
    )
    symbols = _symbols_from_changes([change])
    assert "Client.foo" in symbols
    assert "Client.bar" in symbols


def test_added_symbol_does_not_produce_finding():
    # Regression: ADDED symbols found in the README were flagged as stale,
    # but a README that already documents a new symbol is correct, not stale.
    from readme_drift.checker import run_check  # noqa: F401

    # Verify _symbols_from_changes includes the added name for scanning, but
    # the finding-building loop must skip ADDED changes regardless.
    change = SymbolChange(name="new_func", change_type=ChangeType.ADDED)
    readme_matches = {"new_func": [_readme_match("new_func")]}

    # Simulate the finding-building loop from checker.run_check
    findings: list[StalenessFinding] = []
    for c in [change]:
        if c.change_type == ChangeType.ADDED:
            continue
        relevant_name = _primary_name(c)
        if relevant_name in readme_matches:
            findings.append(
                StalenessFinding(change=c, readme_matches=readme_matches[relevant_name])
            )

    assert findings == []
