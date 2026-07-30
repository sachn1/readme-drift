"""Package-wide constants and default configuration values."""

# ---------------------------------------------------------------------------
# README discovery
# ---------------------------------------------------------------------------

README_EXTENSIONS: tuple[str, ...] = (".md", ".markdown", ".rst", ".txt", "")

README_NAMES: frozenset[str] = frozenset(f"readme{ext}" for ext in README_EXTENSIONS)

# Directories never searched during recursive README discovery.
README_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        ".tox",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".mypy_cache",
    }
)

# ---------------------------------------------------------------------------
# Noise blocklist — plain-text matching suppression
# ---------------------------------------------------------------------------
# Tokens suppressed from plain-text (word-boundary) README matching.
# Categorised for traceability — each group explains why the words are noisy.
# Tokens are still matched when they appear inside backtick spans.
#
# Override entirely via ``noise-blocklist`` in ``[tool.readme-drift]``.
# Set to ``[]`` to disable noise suppression.

# Boolean / null literals — saturate prose with no documentary signal.
_NOISE_LITERALS: frozenset[str] = frozenset(
    {
        "true",
        "false",
        "none",
        "null",
        "yes",
        "no",
        "on",
        "off",
    }
)

# Generic infrastructure key names present in almost every config file.
_NOISE_INFRA: frozenset[str] = frozenset(
    {
        "name",
        "version",
        "type",
        "url",
        "host",
        "port",
        "path",
        "file",
        "dir",
        "key",
        "value",
        "data",
        "list",
        "mode",
        "id",
        "tag",
        "ref",
        "src",
        "api",
    }
)

# Common build / CI command verbs that appear constantly in prose context.
_NOISE_COMMANDS: frozenset[str] = frozenset(
    {
        "run",
        "build",
        "test",
        "lint",
        "debug",
        "env",
        "log",
        "use",
    }
)

DEFAULT_NOISE_BLOCKLIST: frozenset[str] = (
    _NOISE_LITERALS | _NOISE_INFRA | _NOISE_COMMANDS
)

# ---------------------------------------------------------------------------
# --init scaffold
# ---------------------------------------------------------------------------
# Bare subheadings only — no generated prose, no scanned symbols. Bootstraps
# something for `readme-drift` to check on the next commit; the project
# still has to write its own docs.
README_TEMPLATE: str = """\
# Project Name

<!--
readme-drift only reliably tracks symbols referenced in backticks, e.g.
`MyClass.my_method`. Plain-text mentions are matched too, but common words
are filtered as noise — wrap public function, class, and config-key names
in backticks below so renames and removals get caught.
-->

## Installation

## Usage

## API Reference

## License
"""

