"""Tests for README scanner module."""

from pathlib import Path

import pytest

from readme_check.scanner import find_symbol_in_readme, scan_readme_for_symbols

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
