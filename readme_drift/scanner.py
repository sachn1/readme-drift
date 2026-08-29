"""Scan README text for references to code symbols."""

import re
from functools import lru_cache
from pathlib import Path

from .models import ReadmeMatch

_BACKTICK_PATTERN_CACHE_SIZE = 2048

# ---------------------------------------------------------------------------
# Mermaid class-diagram detection
# ---------------------------------------------------------------------------
# ```mermaid classDiagram``` blocks are a structural, code-like surface —
# class/method names inside them carry the same precision signal as a
# backtick span, not free prose. Matches inside a detected block therefore
# bypass noise suppression and --no-plain-text-search entirely, same as
# backticks, rather than being treated as ordinary plain-text mentions.

_MERMAID_FENCE_START_RE = re.compile(r"^\s*```\s*mermaid\s*$")
_FENCE_END_RE = re.compile(r"^\s*```\s*$")


def _find_mermaid_class_diagram_lines(lines: list[str]) -> frozenset[int]:
    """Return 1-indexed line numbers inside a ```mermaid classDiagram``` block.

    Only blocks whose first non-blank line is ``classDiagram`` are included —
    other mermaid diagram types (flowchart, sequence, etc.) are not source
    code and are left to ordinary prose matching.
    """
    result: set[int] = set()
    in_fence = False
    is_class_diagram = False
    buffer: list[int] = []

    for i, line in enumerate(lines, start=1):
        if not in_fence:
            if _MERMAID_FENCE_START_RE.match(line):
                in_fence = True
                is_class_diagram = False
                buffer = []
            continue

        if _FENCE_END_RE.match(line):
            if is_class_diagram:
                result.update(buffer)
            in_fence = False
            continue

        buffer.append(i)
        if not is_class_diagram and line.strip().startswith("classDiagram"):
            is_class_diagram = True

    return frozenset(result)


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
    mermaid_lines: frozenset[int] = frozenset(),
) -> list[ReadmeMatch]:
    """Search pre-split lines for a symbol using cached compiled patterns."""
    patterns = _patterns_for(symbol_name, plain_text=plain_text)
    # Mermaid class diagrams nest methods inside their class block
    # (`class Job { +run() }`), never as a dotted "Job.run" string, so
    # match on the leaf segment rather than the full qualified name.
    leaf_name = _normalize(symbol_name).rsplit(".", 1)[-1]
    mermaid_pattern = _plain_text_pattern(leaf_name)
    matches: list[ReadmeMatch] = []

    for line_num, line in enumerate(lines, start=1):
        match = None
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                break

        # Mermaid class-diagram lines are checked unconditionally — same
        # trust tier as backticks, independent of plain_text/noise settings.
        if match is None and line_num in mermaid_lines:
            match = mermaid_pattern.search(line)

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
    - Occurrences inside a ```mermaid classDiagram``` block (always matched,
      regardless of plain_text — same trust tier as backticks)
    """
    assert symbol_name, "symbol_name must not be empty"

    if not readme_path.exists():
        return []

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    mermaid_lines = _find_mermaid_class_diagram_lines(lines)
    return _search_lines(
        lines, readme_path, symbol_name, plain_text=plain_text, mermaid_lines=mermaid_lines
    )


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
        A set of symbol names that must only be matched inside backtick spans
        (or a mermaid class-diagram block), even when plain_text=True. Used
        by the noise-suppression layer to restrict short or common tokens to
        the more precise matches.
    """
    if not readme_path.exists():
        return {}

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    mermaid_lines = _find_mermaid_class_diagram_lines(lines)
    _backtick_only = force_backtick_only or set()

    results: dict[str, list[ReadmeMatch]] = {}
    for symbol in symbols:
        use_plain = plain_text and symbol not in _backtick_only
        matches = _search_lines(
            lines, readme_path, symbol, plain_text=use_plain, mermaid_lines=mermaid_lines
        )
        if matches:
            results[symbol] = matches

    return results
