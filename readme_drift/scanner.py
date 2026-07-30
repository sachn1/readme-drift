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
    """Compiled backtick-span pattern for a symbol, memoized per name.

    Symbol names repeat across README files (monorepos) and across
    subsequent runs within the same process, so caching the compiled
    pattern avoids re-compiling identical regex for every (readme, symbol)
    pair.
    """
    return re.compile(rf"`{re.escape(bare_name)}[^`]*`")


@lru_cache(maxsize=_BACKTICK_PATTERN_CACHE_SIZE)
def _plain_text_pattern(bare_name: str) -> re.Pattern[str]:
    """Compiled word-boundary pattern for a symbol, memoized per name."""
    return re.compile(rf"\b{re.escape(bare_name)}\b")


def _patterns_for(symbol_name: str, *, plain_text: bool) -> list[re.Pattern[str]]:
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

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    return _search_lines(lines, readme_path, symbol_name, plain_text=plain_text)


def scan_readme_for_symbols(
    readme_path: Path,
    symbols: list[str],
    *,
    plain_text: bool = True,
    force_backtick_only: set[str] | None = None,
) -> dict[str, list[ReadmeMatch]]:
    """
    Scan README for multiple symbols.

    Returns a dict of symbol → list of matches.
    Only symbols that ARE found in the README are included.

    The file is read and split into lines once, then reused for every
    symbol — avoids re-reading and re-splitting the same README once per
    symbol, which otherwise dominates cost on repos with many changes.

    Parameters
    ----------
    force_backtick_only:
        A set of symbol names that must only be matched inside backtick spans,
        even when plain_text=True.  Used by the noise-suppression layer to
        restrict short or common tokens to the more precise backtick match.
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
