"""Generate the scenario images in docs/assets/scenarios from real tool runs."""

# Run `make cards` (or `python tests/scenario_cards.py`) to rewrite them.

import difflib
import tempfile
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from scenarios import (
    SCENARIOS,
    VERIFY_SCENARIOS,
    run_scenario,
    run_verify_scenario,
)

from readme_drift.report import format_report, format_verify_report

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "assets" / "scenarios"

# id -> (title, badge label, badge colour, why-note shown under the panels).
# Order is the gallery order. Diff-mode scenarios come from SCENARIOS, --verify
# scenarios from VERIFY_SCENARIOS.
CARDS: dict[str, tuple[str, str, str, str]] = {
    "py-rename": (
        "Rename a function",
        "CAUGHT",
        "#238636",
        "connect no longer exists, but the README still tells readers to call it. "
        "The old name is found in the README, so the commit is flagged.",
    ),
    "config-ci-job-renamed": (
        "Rename a CI job",
        "CAUGHT",
        "#238636",
        "Config files are compared too. The integration job is gone, but the README "
        "still describes it, so it is flagged.",
    ),
    "mermaid-class-renamed": (
        "Rename a class shown in a mermaid diagram",
        "CAUGHT",
        "#238636",
        "Names inside a mermaid classDiagram are matched like backtick spans, so "
        "the stale Client in the diagram is found.",
    ),
    "py-body-only-change": (
        "Change behaviour, keep the signature",
        "NOT TRACKED",
        "#6e7681",
        "The signature is identical, so nothing looks changed. Only names and "
        "signatures are compared, not what the code does.",
    ),
    "false-positive-backtick-prefix": (
        "Remove connect, README mentions connection_pool",
        "FALSE ALARM (known gap)",
        "#b62324",
        "connection_pool has nothing to do with connect, but a backtick span that "
        "merely starts with the removed name is treated as a match.",
    ),
    "verify-make-build": (
        "--verify: a command in a sentence and in a code block",
        "CAUGHT WITH --verify",
        "#238636",
        "make build appears twice and both are checked against the Makefile. "
        "Diff mode alone misses this, because build is a very common word.",
    ),
    "verify-code-block": (
        "--verify: every command in a code block",
        "CAUGHT WITH --verify",
        "#238636",
        "Each line, each chained command and each argument is checked, not just "
        "the first word: two missing names are found among the working ones.",
    ),
    "verify-unverifiable": (
        "--verify: when it is not sure, it does not fail",
        "UNVERIFIABLE, NOT FAILED",
        "#6e7681",
        "A placeholder and a command after cd cannot be checked, so they are "
        "reported as unverifiable. The block under the ignore marker is skipped.",
    ),
}

_WIDTH_CHARS = 88
_CHAR_W = 7.9
_LINE_H = 19
_PAD = 22
_BG = "#0d1117"
_PANEL = "#161b22"
_TEXT = "#e6edf3"
_MUTED = "#8b949e"
_ADD = "#7ee787"
_DEL = "#ff7b72"
_FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def _wrap(line: str) -> list[str]:
    """Wrap a line at word boundaries so it fits the card width."""
    if len(line) <= _WIDTH_CHARS:
        return [line]
    lead = len(line) - len(line.lstrip(" "))
    return textwrap.wrap(
        line,
        width=_WIDTH_CHARS,
        subsequent_indent=" " * (lead + 2),
        break_long_words=True,
        drop_whitespace=True,
    )


def _diff_lines(old: dict[str, str], new: dict[str, str]) -> list[tuple[str, str]]:
    """Return (kind, text) lines showing what changed across files."""
    out: list[tuple[str, str]] = []
    for name in sorted(new):
        before, after = old.get(name, ""), new[name]
        if before == after:
            continue
        out.append(("head", name))
        diff = difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm="", n=1
        )
        for line in list(diff)[2:]:
            if line.startswith("@@"):
                continue
            kind = {"+": "add", "-": "del"}.get(line[0], "ctx")
            out.append((kind, line))
    return out


def _file_lines(files: dict[str, str]) -> list[tuple[str, str]]:
    """Return (kind, text) lines listing each repository file and its content."""
    out: list[tuple[str, str]] = []
    for name in files:
        out.append(("head", name))
        out.extend(
            ("txt", line.replace("\t", "    ")) for line in files[name].splitlines()
        )
    return out


def _panel(title: str, lines: list[tuple[str, str]], y: int) -> tuple[str, int]:
    """Return (svg, height) for one titled panel starting at y."""
    body: list[tuple[str, str]] = []
    for kind, text in lines:
        for chunk in _wrap(text):
            body.append((kind, chunk))
    height = 34 + len(body) * _LINE_H + 12
    width = _PAD * 2 + int(_WIDTH_CHARS * _CHAR_W)
    parts = [
        f'<rect x="{_PAD}" y="{y}" width="{width - 2 * _PAD}" height="{height}" '
        f'rx="8" fill="{_PANEL}"/>',
        f'<text x="{_PAD + 14}" y="{y + 22}" fill="{_MUTED}" font-size="11" '
        f'letter-spacing="0.5">{escape(title)}</text>',
    ]
    colours = {"add": _ADD, "del": _DEL, "head": _MUTED, "ctx": _TEXT, "txt": _TEXT}
    for i, (kind, text) in enumerate(body):
        ty = y + 44 + i * _LINE_H
        if not text.strip():
            continue
        parts.append(
            f'<text x="{_PAD + 14}" y="{ty}" fill="{colours[kind]}" '
            f'xml:space="preserve">{escape(text)}</text>'
        )
    return "\n".join(parts), height


def render_card(name: str) -> str:
    """Run a scenario for real and return its SVG card as text."""
    title, badge, badge_colour, note = CARDS[name]
    with tempfile.TemporaryDirectory() as tmp:
        if name in VERIFY_SCENARIOS:
            files, readme_text, _expected = VERIFY_SCENARIOS[name]
            output_text = format_verify_report(run_verify_scenario(name, Path(tmp)))
            first = ("The repo has", _file_lines(files))
            readme_lines = [("txt", ln) for ln in readme_text.rstrip("\n").splitlines()]
            output_label = "readme-drift --verify says"
        else:
            old, new, readme, _kw, _expected, _hint = SCENARIOS[name]
            output_text = format_report(run_scenario(name, Path(tmp)))
            first = ("You change", _diff_lines(old, new))
            readme_lines = [("txt", ln) for ln in readme[-1].rstrip("\n").splitlines()]
            output_label = "readme-drift says"
    output = [("txt", line) for line in output_text.splitlines()]

    width = _PAD * 2 + int(_WIDTH_CHARS * _CHAR_W)
    y = 62
    panels = []
    for label, lines in (
        first,
        ("README.md says", readme_lines),
        (output_label, output),
    ):
        svg, h = _panel(label, lines, y)
        panels.append(svg)
        y += h + 12
    if note:
        svg, h = _panel(
            "Why", [("txt", line) for line in textwrap.wrap(note, _WIDTH_CHARS)], y
        )
        panels.append(svg)
        y += h + 12
    height = y + 10
    badge_w = int(len(badge) * 7.6 + 24)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}" font-size="13" '
        f'role="img" aria-label="{escape(title)}: {escape(badge)}">\n'
        f'<rect width="{width}" height="{height}" rx="12" fill="{_BG}"/>\n'
        f'<text x="{_PAD}" y="38" fill="{_TEXT}" font-size="16" '
        f'font-weight="bold">{escape(title)}</text>\n'
        f'<rect x="{width - _PAD - badge_w}" y="20" width="{badge_w}" height="26" '
        f'rx="13" fill="{badge_colour}"/>\n'
        f'<text x="{width - _PAD - badge_w / 2}" y="37" fill="#ffffff" '
        f'font-size="11" font-weight="bold" text-anchor="middle">{escape(badge)}</text>\n'
        + "\n".join(panels)
        + "\n</svg>\n"
    )


def main() -> None:
    """Write every scenario card to docs/assets/scenarios."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in CARDS:
        (OUT_DIR / f"{name}.svg").write_text(render_card(name), encoding="utf-8")
        print(f"wrote {OUT_DIR / (name + '.svg')}")


if __name__ == "__main__":
    main()
