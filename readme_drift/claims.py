"""Extract shell-command claims from README code blocks and inline code spans."""

import re
import shlex
from pathlib import Path

from .models import Claim

IGNORE_MARKER = "<!-- readme-drift: ignore -->"

# Fence languages treated as shell. An untagged fence is included on purpose.
_SHELL_LANGS = frozenset(
    {"", "bash", "sh", "shell", "zsh", "console", "shell-session", "shellsession"}
)
# Languages where only lines starting with "$ " are commands (the rest is output).
_PROMPT_LANGS = frozenset({"console", "shell-session", "shellsession"})

_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")"})
_REDIRECT_RE = re.compile(r"^[<>&]+$")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_COMMAND_NAME_RE = re.compile(r"^[A-Za-z0-9_./+-]+$")
_ANGLE_PLACEHOLDER_RE = re.compile(r"<[^<>\s]+>")
_WRAPPERS = frozenset({"sudo", "time", "nohup", "exec", "command"})
_RUNNER_PREFIXES = frozenset({("poetry", "run"), ("uv", "run"), ("pipenv", "run")})
_CWD_COMMANDS = frozenset({"cd", "pushd", "popd"})

# Inline code spans: a run of backticks closed by a run of the same length, which
# may continue over several lines of one paragraph (CommonMark).
_INLINE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
_SCRIPT_EXTS = (".py", ".sh", ".bash")
_JS_RUNNERS = frozenset({"npm", "pnpm", "yarn"})
_PYTHON_HEAD_RE = re.compile(r"^python[0-9.]*$")
_SHELL_HEADS = frozenset({"bash", "sh", "zsh", "source"})


def _is_placeholder(token: str) -> bool:
    """Return True for tokens that stand for a value rather than a real one."""
    return (
        "$" in token
        or token in {"...", "…"}
        or bool(_ANGLE_PLACEHOLDER_RE.search(token))
    )


def _tokenize(line: str) -> list[str] | None:
    """Split a shell line into tokens, or None if it cannot be parsed."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def _split_segments(tokens: list[str]) -> list[list[str]]:
    """Split tokens on command separators and drop redirections."""
    segments: list[list[str]] = [[]]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in _SEPARATORS:
            segments.append([])
        elif _REDIRECT_RE.match(token):
            if segments[-1] and segments[-1][-1].isdigit():
                segments[-1].pop()
            skip_next = True
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _strip_prefixes(segment: list[str]) -> list[str]:
    """Remove env assignments, wrappers (``sudo``) and runners (``poetry run``)."""
    tokens = list(segment)
    changed = True
    while tokens and changed:
        changed = False
        if _ASSIGNMENT_RE.match(tokens[0]) or tokens[0] in _WRAPPERS:
            tokens = tokens[1:]
            changed = True
        elif len(tokens) >= 2 and tuple(tokens[:2]) in _RUNNER_PREFIXES:
            tokens = tokens[2:]
            changed = True
    return tokens


def _heredoc_delimiter(tokens: list[str]) -> str | None:
    """Return the heredoc delimiter if the line starts a heredoc."""
    for i, token in enumerate(tokens[:-1]):
        if token in {"<<", "<<-"}:
            return tokens[i + 1]
    return None


def _previous_is_marker(lines: list[str], index: int) -> bool:
    """Return True if the closest preceding non-blank line is the ignore marker."""
    j = index - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    return j >= 0 and lines[j].strip() == IGNORE_MARKER


def _is_closing_fence(line: str, char: str, length: int) -> bool:
    """Return True if a line closes a fence opened with ``length`` of ``char``."""
    return bool(re.match(rf"^\s*{re.escape(char)}{{{length},}}\s*$", line))


def _join_continuations(lines: list[str], index: int) -> tuple[str, int]:
    """Join backslash-continued lines; return the text and the next index."""
    text = lines[index]
    index += 1
    while text.rstrip().endswith("\\") and index < len(lines):
        text = text.rstrip()[:-1] + " " + lines[index].strip()
        index += 1
    return text, index


def _claims_from_line(
    text: str,
    readme_path: Path,
    line_number: int,
    cwd_changed: bool,
) -> tuple[list[Claim], bool, str | None]:
    """Build claims from one logical line; return them, the cwd flag and heredoc."""
    tokens = _tokenize(text)
    if tokens is None:
        return [], cwd_changed, None
    heredoc = _heredoc_delimiter(tokens)
    claims: list[Claim] = []
    for segment in _split_segments(tokens):
        stripped = _strip_prefixes(segment)
        if (
            not stripped
            or _is_placeholder(stripped[0])
            or not _COMMAND_NAME_RE.match(stripped[0])
        ):
            continue
        head = stripped[0]
        args = tuple(t for t in stripped[1:] if not _is_placeholder(t))
        claims.append(
            Claim(
                head=head,
                args=args,
                raw=" ".join(stripped),
                readme_path=readme_path,
                line_number=line_number,
                cwd_changed=cwd_changed,
            )
        )
        if head in _CWD_COMMANDS:
            cwd_changed = True
    return claims, cwd_changed, heredoc


def _prose_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Return (first line index, lines) for each paragraph outside code fences."""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start = 0
    fence: tuple[str, int] | None = None

    def flush() -> None:
        """Close the paragraph being collected, if any."""
        nonlocal current
        if current:
            blocks.append((start, current))
        current = []

    for index, line in enumerate(lines):
        if fence is not None:
            if _is_closing_fence(line, *fence):
                fence = None
            continue
        opening = _FENCE_OPEN_RE.match(line)
        if opening:
            flush()
            fence = (opening.group(1)[0], len(opening.group(1)))
            continue
        if not line.strip():
            flush()
            continue
        if not current:
            start = index
        current.append(line)
    flush()
    return blocks


def _inline_eligible(claim: Claim, entry_points: frozenset[str]) -> bool:
    """Return True if an inline span clearly reads as a command worth verifying."""
    head, args = claim.head, claim.args
    if head in {"make", "gmake"}:
        return bool(args)
    if head in _JS_RUNNERS:
        return len(args) >= 2 and args[0] in {"run", "run-script"}
    if head == "docker":
        return len(args) >= 2 and args[0] == "compose"
    if head == "docker-compose":
        return bool(args)
    if _PYTHON_HEAD_RE.match(head) or head in _SHELL_HEADS:
        return any(arg.endswith(_SCRIPT_EXTS) for arg in args)
    if head.startswith("./"):
        return head.endswith(_SCRIPT_EXTS)
    if head in entry_points:
        return bool(args) and args[0].startswith("-")
    return False


def _inline_claims(
    lines: list[str], readme_path: Path, entry_points: frozenset[str]
) -> list[Claim]:
    """Extract claims from inline code spans that clearly read as commands."""
    claims: list[Claim] = []
    for start, block in _prose_blocks(lines):
        if block[0].strip() == IGNORE_MARKER:
            continue
        text = "\n".join(block)
        for match in _INLINE_SPAN_RE.finditer(text):
            span = " ".join(match.group(2).split())
            line_number = start + 1 + text.count("\n", 0, match.start())
            found, _, _ = _claims_from_line(span, readme_path, line_number, False)
            claims.extend(c for c in found if _inline_eligible(c, entry_points))
    return claims


def extract_claims(
    readme_path: Path, entry_points: frozenset[str] | None = None
) -> list[Claim]:
    """Extract shell-command claims from a Markdown README.

    Only fences tagged ``bash``, ``sh``, ``shell``, ``zsh``, ``console`` (or
    untagged) are read. Prompts (``$ ``), backslash continuations,
    ``&&`` / ``;`` / ``|`` chains and redirections are handled. Placeholder
    tokens (``<name>``, ``$VAR``, ``...``) are dropped from the arguments, and
    a block (or a single command) preceded by ``<!-- readme-drift: ignore -->``
    is skipped.

    Inline code spans in prose are read too, but only when they clearly are
    commands: ``make <target>``, ``npm|pnpm|yarn run <script>``,
    ``docker compose ...``, a Python or shell script with a file extension, or
    one of the project's own commands followed by a flag. A span may continue
    over several lines of a paragraph. A paragraph whose first line is the
    ignore marker is skipped.

    Parameters
    ----------
    readme_path : Path
        README file to read.
    entry_points : frozenset[str] or None, optional
        Names of the project's console scripts, so ``` `mytool --flag` ``` in
        prose counts as a command; None disables that case.

    Returns
    -------
    list[Claim]
        One claim per command found; empty if the file is absent.
    """
    if not readme_path.exists():
        return []
    lines = readme_path.read_text(encoding="utf-8").splitlines()

    claims: list[Claim] = []
    fence: tuple[str, int, str] | None = None
    ignore_block = False
    ignore_next = False
    cwd_changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if fence is None:
            match = _FENCE_OPEN_RE.match(line)
            if match:
                info = match.group(2).strip()
                lang = info.split()[0].lower() if info else ""
                fence = (match.group(1)[0], len(match.group(1)), lang)
                ignore_block = _previous_is_marker(lines, i)
                ignore_next = False
                cwd_changed = False
            i += 1
            continue

        char, length, lang = fence
        if _is_closing_fence(line, char, length):
            fence = None
            i += 1
            continue
        if lang not in _SHELL_LANGS or ignore_block or not line.strip():
            i += 1
            continue
        if line.strip() == IGNORE_MARKER:
            ignore_next = True
            i += 1
            continue

        start = i + 1
        text, i = _join_continuations(lines, i)
        stripped = text.strip()
        if lang in _PROMPT_LANGS:
            if not stripped.startswith("$ "):
                continue
        if stripped.startswith("$ "):
            stripped = stripped[2:]
        if stripped.startswith("#"):
            continue
        if ignore_next:
            ignore_next = False
            continue

        found, cwd_changed, heredoc = _claims_from_line(
            stripped, readme_path, start, cwd_changed
        )
        claims.extend(found)
        if heredoc is not None:
            while i < len(lines) and lines[i].strip() != heredoc:
                i += 1
            i += 1
    claims.extend(_inline_claims(lines, readme_path, entry_points or frozenset()))
    return sorted(claims, key=lambda claim: claim.line_number)
