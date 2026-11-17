"""Scan README text for references to code symbols."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .models import ReadmeMatch

_BACKTICK_PATTERN_CACHE_SIZE = 2048

# ---------------------------------------------------------------------------
# Mermaid class-diagram matching
# ---------------------------------------------------------------------------
# ```mermaid classDiagram``` blocks are a structural, code-like surface, so
# names inside them are matched by structure rather than as free prose, and
# bypass noise suppression and --no-plain-text-search:
#   - a bare name matches only if it is a *class* in that diagram;
#   - ``Class.method`` matches only on lines that belong to that class.
# Functions and config keys never match through a diagram (they still match
# as ordinary prose under the usual noise rules).

_MERMAID_FENCE_START_RE = re.compile(r"^\s*```\s*mermaid\s*$")
_FENCE_END_RE = re.compile(r"^\s*```\s*$")
_CLASS_DECL_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)")
_MEMBER_OWNER_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:")
_RELATION_RE = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*(?:"[^"]*"\s*)?'
    r"(?:<\|--|\*--|o--|-->|<--|--\|>|--\*|--o|\.\.>|<\.\.|\.\.\|>|<\|\.\.|--|\.\.)"
    r'\s*(?:"[^"]*"\s*)?([A-Za-z_]\w*)'
)


@dataclass(frozen=True)
class _ClassDiagram:
    """One mermaid classDiagram block: its line numbers, classes and member owners."""

    lines: frozenset[int]
    classes: frozenset[str]
    owners: dict[int, str]


def _build_class_diagram(body: list[tuple[int, str]]) -> _ClassDiagram:
    """Parse the lines of a classDiagram block into classes and member owners."""
    classes: set[str] = set()
    owners: dict[int, str] = {}
    current: str | None = None
    for line_no, text in body:
        if text.strip() == "}":
            current = None
            continue
        decl = _CLASS_DECL_RE.match(text)
        if decl:
            classes.add(decl.group(1))
            current = decl.group(1) if text.rstrip().endswith("{") else None
            continue
        if current:
            owners[line_no] = current
            continue
        owner = _MEMBER_OWNER_RE.match(text)
        if owner:
            classes.add(owner.group(1))
            owners[line_no] = owner.group(1)
            continue
        relation = _RELATION_RE.match(text)
        if relation:
            classes.update(relation.groups())
    return _ClassDiagram(
        frozenset(line_no for line_no, _ in body), frozenset(classes), owners
    )


def _parse_class_diagrams(lines: list[str]) -> tuple[_ClassDiagram, ...]:
    """Return every mermaid classDiagram block in a README, parsed for matching."""
    diagrams: list[_ClassDiagram] = []
    body: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if not in_fence:
            if _MERMAID_FENCE_START_RE.match(line):
                in_fence = True
                body = []
            continue
        if _FENCE_END_RE.match(line):
            in_fence = False
            if any(text.strip().startswith("classDiagram") for _, text in body):
                diagrams.append(_build_class_diagram(body))
            continue
        body.append((i, line))
    return tuple(diagrams)


def _diagram_match(
    symbol: str, line_no: int, line: str, diagrams: tuple[_ClassDiagram, ...]
) -> re.Match[str] | None:
    """Return a match for a symbol on a class-diagram line, scoped to its class."""
    owner, _, leaf = symbol.rpartition(".")
    for diagram in diagrams:
        if line_no not in diagram.lines:
            continue
        if owner:
            if diagram.owners.get(line_no) == owner:
                return _plain_text_pattern(leaf).search(line)
        elif symbol in diagram.classes:
            if diagram.owners.get(line_no, symbol) == symbol:
                return _plain_text_pattern(symbol).search(line)
    return None


def _normalize(name: str) -> str:
    """Strip trailing () or leading/trailing punctuation for loose matching."""
    return name.strip("()").strip()


@lru_cache(maxsize=_BACKTICK_PATTERN_CACHE_SIZE)
def _backtick_pattern(bare_name: str) -> re.Pattern[str]:
    """Return the compiled backtick-span pattern for a name, memoized."""
    return re.compile(rf"`{re.escape(bare_name)}(?![\w-])[^`]*`")


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


_CLASS_METHOD_RE = re.compile(r"^([A-Z][A-Za-z0-9]*)\.([A-Za-z_][A-Za-z0-9_]*)$")
_CAMEL_BREAK_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@lru_cache(maxsize=_BACKTICK_PATTERN_CACHE_SIZE)
def _instance_pattern(bare_name: str) -> re.Pattern[str] | None:
    """Return a pattern for receiver.method( calls of a Class.method symbol, if any."""
    # The receiver must be the class name in lowercase or snake_case (Console gives
    # console), stand alone as a word, and be followed by a call.
    match = _CLASS_METHOD_RE.match(bare_name)
    if not match:
        return None
    cls, method = match.groups()
    receivers = {cls.lower(), _CAMEL_BREAK_RE.sub("_", cls).lower()}
    alternatives = "|".join(re.escape(r) for r in sorted(receivers))
    return re.compile(rf"(?<![\w])(?:{alternatives})\.{re.escape(method)}\s*\(")


_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_COMMENT_RE = re.compile(r"(^|\s)#.*$")


def _fenced_code_lines(lines: list[str]) -> frozenset[int]:
    """Return 1-indexed line numbers inside fenced code blocks, markers excluded."""
    inside: set[int] = set()
    fence: tuple[str, int] | None = None
    for number, line in enumerate(lines, start=1):
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = (match.group(1)[0], len(match.group(1)))
            continue
        closes = (
            match
            and match.group(1)[0] == fence[0]
            and len(match.group(1)) >= fence[1]
            and not line.strip().strip(fence[0])
        )
        if closes:
            fence = None
        else:
            inside.add(number)
    return frozenset(inside)


def _code_context_match(
    name: str, line: str, line_number: int, code_lines: frozenset[int]
) -> re.Match[str] | None:
    """Match a name only where it is code: in an inline span or a fenced code line."""
    word = _plain_text_pattern(name)
    if line_number in code_lines:
        return word.search(_COMMENT_RE.sub("", line))
    for span in _INLINE_CODE_RE.finditer(line):
        if word.search(span.group(1)):
            return span
    return None


def _search_lines(
    lines: list[str],
    readme_path: Path,
    symbol_name: str,
    *,
    plain_text: bool,
    diagrams: tuple[_ClassDiagram, ...] = (),
    code_only: bool = False,
    code_lines: frozenset[int] = frozenset(),
) -> list[ReadmeMatch]:
    """Search pre-split lines for a symbol using cached compiled patterns."""
    patterns = _patterns_for(symbol_name, plain_text=plain_text)
    bare_name = _normalize(symbol_name)
    instance = _instance_pattern(bare_name)
    matches: list[ReadmeMatch] = []

    for line_num, line in enumerate(lines, start=1):
        match = None
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                break

        # An instance call such as ``console.print(`` references ``Console.print``.
        if match is None and instance is not None:
            match = instance.search(line)

        # Class-diagram lines are matched structurally, independent of the
        # plain_text and noise settings (same trust tier as backticks).
        if match is None and diagrams:
            match = _diagram_match(bare_name, line_num, line, diagrams)

        # Code-only symbols (config keys, Makefile targets) match inside inline
        # code or a fenced code line, never in ordinary prose.
        if match is None and code_only:
            match = _code_context_match(bare_name, line, line_num, code_lines)

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
    """Search a README file for references to a symbol name.

    Matches exact backtick references (``Class.method``) and, when enabled,
    plain-text occurrences using a word-boundary match. Inside a mermaid
    ``classDiagram`` block a class name matches that class, and ``Class.method``
    matches only on lines belonging to that class, regardless of
    ``plain_text``.

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
    diagrams = _parse_class_diagrams(lines)
    return _search_lines(
        lines,
        readme_path,
        symbol_name,
        plain_text=plain_text,
        diagrams=diagrams,
    )


def scan_readme_for_symbols(
    readme_path: Path,
    symbols: list[str],
    *,
    plain_text: bool = True,
    force_backtick_only: set[str] | None = None,
    code_only_symbols: set[str] | None = None,
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
        True. Used by noise suppression for short or common tokens. Class-diagram
        matches are structural and not affected.
    code_only_symbols : set[str] or None, optional
        Symbols matched only in code (an inline span or a fenced code line),
        never in plain prose. Used for config keys and Makefile targets. A
        symbol also in ``force_backtick_only`` keeps the stricter rule.

    Returns
    -------
    dict[str, list[ReadmeMatch]]
        Mapping of symbol to its matches; symbols not found are omitted.
    """
    if not readme_path.exists():
        return {}

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    diagrams = _parse_class_diagrams(lines)
    _backtick_only = force_backtick_only or set()
    _code_only = code_only_symbols or set()
    code_lines = _fenced_code_lines(lines) if _code_only else frozenset()

    results: dict[str, list[ReadmeMatch]] = {}
    for symbol in symbols:
        restricted = symbol in _backtick_only
        code_only = symbol in _code_only and not restricted
        use_plain = plain_text and not restricted and not code_only
        matches = _search_lines(
            lines,
            readme_path,
            symbol,
            plain_text=use_plain,
            diagrams=diagrams,
            code_only=code_only,
            code_lines=code_lines,
        )
        if matches:
            results[symbol] = matches

    return results
