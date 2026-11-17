"""Scan README text for references to code symbols."""

import re
from functools import lru_cache
from pathlib import Path

from .models import ReadmeMatch

_BACKTICK_PATTERN_CACHE_SIZE = 2048


def _normalize(name: str) -> str:
    """Strip trailing () or leading/trailing punctuation for loose matching."""
    return name.strip("()").strip()


@lru_cache(maxsize=_BACKTICK_PATTERN_CACHE_SIZE)
def _backtick_pattern(bare_name: str) -> re.Pattern[str]:
    """Return the compiled backtick-span pattern for a name, memoized."""
    return re.compile(rf"`{re.escape(bare_name)}[^`]*`")


@lru_cache(maxsize=_BACKTICK_PATTERN_CACHE_SIZE)
def _plain_text_pattern(bare_name: str) -> re.Pattern[str]:
    """Compiled word-boundary pattern for a symbol, memoized per name."""
    return re.compile(rf"\b{re.escape(bare_name)}\b")


def _patterns_for(symbol_name: str, *, plain_text: bool) -> list[re.Pattern[str]]:
    """Return the compiled patterns used to search for a symbol."""
    bare_name = _normalize(symbol_name)
    patterns = [_backtick_pattern(bare_name)]
    if plain_text:
        patterns.append(_plain_text_pattern(bare_name))
    return patterns


def _search_lines(
    lines: list[str],
    readme_path: Path,
    symbol_name: str,
    *,
    plain_text: bool,
) -> list[ReadmeMatch]:
    """Search pre-split lines for a symbol using cached compiled patterns."""
    patterns = _patterns_for(symbol_name, plain_text=plain_text)
    matches: list[ReadmeMatch] = []

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


def find_symbol_in_readme(
    readme_path: Path,
    symbol_name: str,
    *,
    plain_text: bool = True,
) -> list[ReadmeMatch]:
    """Search a README file for references to a symbol name.

    Matches exact backtick references (``Class.method``) and, when enabled,
    plain-text occurrences using a word-boundary match.

    Parameters
    ----------
    readme_path : Path
        README file to search.
    symbol_name : str
        Symbol to look for; must not be empty.
    plain_text : bool, optional
        Also match plain-text occurrences, by default True.

    Returns
    -------
    list[ReadmeMatch]
        One match per matching line; empty if the file is absent or nothing matches.
    """
    assert symbol_name, "symbol_name must not be empty"

    if not readme_path.exists():
        return []

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    return _search_lines(lines, readme_path, symbol_name, plain_text=plain_text)


def scan_readme_for_symbols(
    readme_path: Path,
    symbols: list[str],
    *,
    plain_text: bool = True,
    force_backtick_only: set[str] | None = None,
) -> dict[str, list[ReadmeMatch]]:
    """Scan a README for references to multiple symbols.

    The file is read and split once, then reused for every symbol.

    Parameters
    ----------
    readme_path : Path
        README file to scan.
    symbols : list[str]
        Symbol names to look for.
    plain_text : bool, optional
        Also match plain-text occurrences, by default True.
    force_backtick_only : set[str] or None, optional
        Symbols restricted to backtick-span matching even when ``plain_text`` is
        True. Used by noise suppression for short or common tokens.

    Returns
    -------
    dict[str, list[ReadmeMatch]]
        Mapping of symbol to its matches; symbols not found are omitted.
    """
    if not readme_path.exists():
        return {}

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    _backtick_only = force_backtick_only or set()

    results: dict[str, list[ReadmeMatch]] = {}
    for symbol in symbols:
        use_plain = plain_text and symbol not in _backtick_only
        matches = _search_lines(lines, readme_path, symbol, plain_text=use_plain)
        if matches:
            results[symbol] = matches

    return results
