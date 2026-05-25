"""Scan README text for references to code symbols."""

import re
from pathlib import Path

from .models import ReadmeMatch


def _normalize(name: str) -> str:
    """Strip trailing () or leading/trailing punctuation for loose matching."""
    return name.strip("()").strip()


def find_symbol_in_readme(
    readme_path: Path,
    symbol_name: str,
) -> list[ReadmeMatch]:
    """
    Search a README file for references to a symbol name.

    Matches:
    - Exact backtick references: `symbol_name`
    - Method references: `Class.method` or `class.method()`
    - Plain text occurrences of the symbol name (word boundary match)
    """
    assert symbol_name, "symbol_name must not be empty"

    if not readme_path.exists():
        return []

    content = readme_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    matches: list[ReadmeMatch] = []
    bare_name = _normalize(symbol_name)

    patterns = [
        re.compile(rf"`{re.escape(bare_name)}[^`]*`"),
        re.compile(rf"\b{re.escape(bare_name)}\b"),
    ]

    for line_num, line in enumerate(lines, start=1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                matches.append(
                    ReadmeMatch(
                        symbol=symbol_name,
                        line_number=line_num,
                        line_text=line.strip(),
                        matched_text=match.group(),
                        readme_path=readme_path,
                    )
                )
                break  # One match per line is enough

    return matches


def scan_readme_for_symbols(
    readme_path: Path,
    symbols: list[str],
) -> dict[str, list[ReadmeMatch]]:
    """
    Scan README for multiple symbols.

    Returns a dict of symbol → list of matches.
    Only symbols that ARE found in the README are included.
    """
    results: dict[str, list[ReadmeMatch]] = {}

    for symbol in symbols:
        matches = find_symbol_in_readme(readme_path, symbol)
        if matches:
            results[symbol] = matches

    return results
