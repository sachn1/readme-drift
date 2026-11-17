"""Keep README, the docs site, the CLI and action.yml consistent with each other."""

import re
import tomllib
from pathlib import Path

import yaml

from readme_drift.cli import main

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CLI_REFERENCE = ROOT / "docs" / "usage" / "cli-reference.md"
CONFIG_DOC = ROOT / "docs" / "configuration.md"
CI_DOC = ROOT / "docs" / "usage" / "ci.md"

# Options that exist on the command line but are not [tool.readme-drift] keys.
_NOT_CONFIG_KEYS = {"init", "repo_root"}
# Config keys with no command-line flag.
_CONFIG_ONLY_KEYS = {"tips"}


def _section(text: str, heading: str) -> str:
    """Return the body of a markdown section from its heading to the next peer."""
    level = heading.split(" ", 1)[0]
    pattern = rf"^{re.escape(heading)}\s*$(.*?)(?=^{level} |\Z)"
    match = re.search(pattern, text, re.S | re.M)
    assert match, f"section {heading!r} not found"
    return match.group(1)


def _table_keys(section: str) -> set[str]:
    """Return the first-column backticked names of every table row."""
    return set(re.findall(r"^\|\s*`([a-z][a-z-]*)`\s*\|", section, re.M))


def _config_keys_from_cli() -> set[str]:
    """Return the config keys implied by the click command's options."""
    keys = {
        p.name.replace("_", "-") for p in main.params if p.name not in _NOT_CONFIG_KEYS
    }
    return keys | _CONFIG_ONLY_KEYS


def _cli_flags() -> set[str]:
    """Return every long flag the click command defines."""
    flags: set[str] = set()
    for param in main.params:
        flags.update(
            o for o in [*param.opts, *param.secondary_opts] if o.startswith("--")
        )
    return flags


def test_readme_config_table_matches_cli():
    """The README configuration table lists exactly the supported config keys."""
    documented = _table_keys(_section(README.read_text(), "## Configuration"))
    assert documented == _config_keys_from_cli()


def test_config_doc_key_reference_matches_cli():
    """The docs-site key reference lists exactly the supported config keys."""
    documented = _table_keys(_section(CONFIG_DOC.read_text(), "## Key reference"))
    assert documented == _config_keys_from_cli()


def test_cli_reference_documents_every_flag_and_nothing_else():
    """The CLI reference has a heading for each flag and none for removed flags."""
    headings = re.findall(r"^### .*$", CLI_REFERENCE.read_text(), re.M)
    documented = {flag for h in headings for flag in re.findall(r"--[a-z][a-z-]*", h)}
    assert documented == _cli_flags() - {"--help"}


def test_version_pins_match_pyproject():
    """Every pinned release in README and docs equals the current version."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["poetry"][
        "version"
    ]
    files = [
        README,
        ROOT / "docs" / "index.md",
        *sorted((ROOT / "docs" / "usage").glob("*.md")),
    ]
    stale = []
    for path in files:
        for pin in re.findall(r"(?:rev:\s*|@)v(\d+\.\d+\.\d+)", path.read_text()):
            if pin != version:
                stale.append(f"{path.relative_to(ROOT)}: v{pin} != v{version}")
    assert stale == []


def test_action_inputs_are_documented_in_ci_doc():
    """Every input declared in action.yml is mentioned on the CI docs page."""
    inputs = yaml.safe_load((ROOT / "action.yml").read_text())["inputs"]
    text = CI_DOC.read_text()
    assert [name for name in inputs if name not in text] == []


def test_scenarios_page_is_linked_from_readme_nav_and_index():
    """The scenarios page exists and is reachable from README, nav and docs home."""
    assert (ROOT / "docs" / "scenarios.md").is_file()
    assert "/scenarios/" in README.read_text()
    assert "scenarios.md" in (ROOT / "mkdocs.yml").read_text()
    assert "scenarios.md" in (ROOT / "docs" / "index.md").read_text()
