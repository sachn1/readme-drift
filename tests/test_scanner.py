"""Tests for README scanner module."""

from pathlib import Path

import pytest

from readme_drift.scanner import find_symbol_in_readme, scan_readme_for_symbols

README_CONTENT = """# My Library

Use `Client.connect(host, port)` to establish a connection.
Then call `Client.disconnect()` when done.

The `helper` function is also available.

For advanced use, see `Client.from_config`.

Plain text mentions of disconnect are also caught.
"""


@pytest.fixture
def readme_file(tmp_path) -> Path:
    path = tmp_path / "README.md"
    path.write_text(README_CONTENT)
    return path


def test_finds_backtick_method(readme_file):
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert len(matches) >= 1
    assert any("connect" in m.matched_text for m in matches)


def test_finds_plain_function(readme_file):
    matches = find_symbol_in_readme(readme_file, "helper")
    assert len(matches) >= 1


def test_finds_plain_text_mention(readme_file):
    matches = find_symbol_in_readme(readme_file, "disconnect")
    assert len(matches) >= 1


def test_no_match_for_unknown_symbol(readme_file):
    matches = find_symbol_in_readme(readme_file, "nonexistent_function")
    assert matches == []


def test_scan_multiple_symbols(readme_file):
    results = scan_readme_for_symbols(
        readme_file,
        ["Client.connect", "helper", "nonexistent"],
    )
    assert "Client.connect" in results
    assert "helper" in results
    assert "nonexistent" not in results


def test_missing_readme(tmp_path):
    matches = find_symbol_in_readme(tmp_path / "README.md", "anything")
    assert matches == []


def test_match_includes_line_number(readme_file):
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert all(m.line_number > 0 for m in matches)


def test_match_includes_line_text(readme_file):
    matches = find_symbol_in_readme(readme_file, "helper")
    assert all(len(m.line_text) > 0 for m in matches)


def test_at_most_one_match_per_line(readme_file):
    # The README has "Plain text mentions of disconnect are also caught."
    # which would match BOTH the backtick pattern AND the word-boundary pattern.
    # find_symbol_in_readme must return at most one ReadmeMatch per line.
    matches = find_symbol_in_readme(readme_file, "disconnect")
    line_numbers = [m.line_number for m in matches]
    assert len(line_numbers) == len(set(line_numbers)), "duplicate matches on same line"


def test_plain_text_false_skips_word_boundary(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Use disconnect to close the connection.\n")
    # The word appears as plain text, not in backticks — plain_text=False should miss it
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert matches == []


def test_plain_text_false_still_matches_backtick(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Call `disconnect` to close.\n")
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert len(matches) == 1


def test_scan_readme_plain_text_false(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Use helper to process data.\n")
    results = scan_readme_for_symbols(readme, ["helper"], plain_text=False)
    assert "helper" not in results
