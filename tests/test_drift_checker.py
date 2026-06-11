"""Tests for checker logic — symbol-to-README matching."""

from pathlib import Path

import pytest

from readme_drift.constants import DEFAULT_NOISE_BLOCKLIST as _DEFAULT_NOISE_BLOCKLIST
from readme_drift.drift_checker import (
    _is_excluded,
    _symbols_from_changes,
)
from readme_drift.models import ChangeType, ReadmeMatch, StalenessFinding, SymbolChange


def _readme_match(symbol: str) -> ReadmeMatch:
    return ReadmeMatch(
        symbol=symbol,
        line_number=5,
        line_text=f"Use `{symbol}` to do things.",
        matched_text=f"`{symbol}`",
        readme_path=Path("README.md"),
    )


def test_added_symbol_does_not_produce_finding():
    # ADDED symbols found in the README must never be flagged as stale —
    # a README that already documents a new symbol is correct, not stale.
    change = SymbolChange(name="new_func", change_type=ChangeType.ADDED)
    readme_matches = {"new_func": [_readme_match("new_func")]}

    findings: list[StalenessFinding] = []
    for c in [change]:
        if c.change_type == ChangeType.ADDED:
            continue
        if c.name in readme_matches:
            findings.append(
                StalenessFinding(change=c, readme_matches=readme_matches[c.name])
            )

    assert findings == []


def test_symbols_from_changes_deduplicates():
    changes = [
        SymbolChange(name="foo", change_type=ChangeType.REMOVED),
        SymbolChange(name="foo", change_type=ChangeType.SIGNATURE_CHANGED),
        SymbolChange(name="bar", change_type=ChangeType.REMOVED),
    ]
    symbols = _symbols_from_changes(changes)
    assert sorted(symbols) == ["bar", "foo"]


@pytest.mark.parametrize(
    "file_str, patterns, expected",
    [
        ("generated/models.py", ["generated/"], True),
        ("src/models.py", ["generated/"], False),
        ("src/models.py", ["*.py"], True),
        ("src/models.py", ["models.py"], True),
        ("src/models.py", ["other.py"], False),
        ("tests/conftest.py", ["tests/"], True),
        ("readme_drift/git.py", ["readme_drift/git.py"], True),
    ],
)
def test_is_excluded(file_str, patterns, expected):
    assert _is_excluded(Path(file_str), patterns) == expected


def test_is_excluded_empty_patterns():
    assert not _is_excluded(Path("src/models.py"), [])


def _run_pipeline_direct(
    old_source,
    new_source,
    readme_text,
    tmp_path,
    *,
    is_config=False,
    filename="client.py",
    symbol_allowlist=None,
    symbol_denylist=None,
    min_symbol_length=4,
    noise_blocklist=None,
    verbose=False,
):
    """Integration helper that bypasses git, wiring the pipeline manually."""
    from readme_drift.ast_diff import diff_apis
    from readme_drift.config_diff import diff_config
    from readme_drift.constants import (
        DEFAULT_NOISE_BLOCKLIST as _DEFAULT_NOISE_BLOCKLIST,
    )
    from readme_drift.drift_checker import (
        _symbols_from_changes,
    )
    from readme_drift.models import DriftCheckResult, StalenessFinding
    from readme_drift.scanner import scan_readme_for_symbols

    readme = tmp_path / "README.md"
    readme.write_text(readme_text)

    changes = (
        diff_config(old_source, new_source, file=filename)
        if is_config
        else diff_apis(old_source, new_source, file=filename)
    )

    _allowlist: set[str] = set(symbol_allowlist or [])
    _denylist: set[str] = set(symbol_denylist or [])
    _blocklist = (
        _DEFAULT_NOISE_BLOCKLIST
        if noise_blocklist is None
        else frozenset(noise_blocklist)
    )

    active = [c for c in changes if c.name not in _denylist]

    force_backtick_only: set[str] = set()
    for change in active:
        if change.name in _allowlist:
            continue
        if change.name in _blocklist or len(change.name) < min_symbol_length:
            force_backtick_only.add(change.name)

    symbols = _symbols_from_changes(active)
    readme_matches = scan_readme_for_symbols(
        readme, symbols, plain_text=True, force_backtick_only=force_backtick_only
    )

    vlog: list[str] = []
    findings: list[StalenessFinding] = []
    for change in active:
        if change.change_type == ChangeType.ADDED:
            if verbose:
                vlog.append(f"{change.name} [added] → additions never stale → skipped")
            continue
        matches = list(readme_matches.get(change.name, []))
        for kp in change.key_paths:
            matches.extend(readme_matches.get(kp, []))
        in_readme = bool(matches)
        on_allowlist = change.name in _allowlist
        if on_allowlist and not in_readme:
            findings.append(StalenessFinding(change=change, readme_matches=[]))
            if verbose:
                vlog.append(f"{change.name} → force-flagged via allowlist")
        elif in_readme:
            findings.append(StalenessFinding(change=change, readme_matches=matches))
            if verbose:
                vlog.append(f"{change.name} → flagged")
        else:
            if verbose:
                vlog.append(f"{change.name} → skipped")

    for change in [c for c in changes if c.name in _denylist]:
        if verbose:
            vlog.append(f"{change.name} → denied")

    return DriftCheckResult(findings=findings, readme_paths=[readme], verbose_log=vlog)


# --- denylist ---


def test_denylist_suppresses_finding(tmp_path):
    old = "def helper(x): pass\n"
    new = "def helper(x, y): pass\n"
    readme = "Use `helper` to process data.\n"

    result = _run_pipeline_direct(
        old, new, readme, tmp_path, symbol_denylist=["helper"]
    )
    assert result.passed
    assert not any(f.symbol == "helper" for f in result.findings)


def test_denylist_does_not_affect_other_symbols(tmp_path):
    old = "def helper(x): pass\ndef important(a): pass\n"
    new = "def helper(x, y): pass\n"
    readme = "Use `helper` and `important`.\n"

    result = _run_pipeline_direct(
        old, new, readme, tmp_path, symbol_denylist=["helper"]
    )
    # helper is denied; important is removed and in README → should be flagged
    assert any(f.symbol == "important" for f in result.findings)


# --- allowlist ---


def test_allowlist_force_flags_even_without_readme_mention(tmp_path):
    old = "def critical_api(x): pass\n"
    new = "def critical_api(x, y): pass\n"
    readme = "# My Project\nNo mention of the API here.\n"

    result = _run_pipeline_direct(
        old, new, readme, tmp_path, symbol_allowlist=["critical_api"]
    )
    assert result.failed
    assert any(f.symbol == "critical_api" for f in result.findings)
    # readme_matches should be empty since it wasn't in README
    flagged = next(f for f in result.findings if f.symbol == "critical_api")
    assert flagged.readme_matches == []


def test_allowlist_bypasses_noise_blocklist(tmp_path):
    # "build" is on the default noise blocklist, but if it's on the allowlist
    # it should be force-flagged even without a backtick match.
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "Run npm build to compile.\n"  # plain-text, no backtick

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
        symbol_allowlist=["build"],
        noise_blocklist=[],  # disable blocklist so plain-text match works normally
    )
    # With empty blocklist the plain-text match for "build" fires → flagged
    assert result.failed


# --- noise suppression ---


def test_blocklisted_symbol_suppressed_in_plain_text(tmp_path):
    # "build" is in the default blocklist.
    # Plain-text mention of "build" in README should NOT produce a finding.
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "Run the build to compile.\n"  # plain text, no backtick

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
    )
    assert result.passed


def test_blocklisted_symbol_still_matched_in_backtick(tmp_path):
    # "build" is in the default blocklist but a backtick reference should still
    # be matched.  The backtick pattern requires the symbol name immediately after
    # the opening backtick, so use "`build`" not "`npm run build`".
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "Run `build` to compile.\n"  # symbol immediately after backtick → matches

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
    )
    assert result.failed
    assert any(f.symbol == "build" for f in result.findings)


def test_min_symbol_length_suppresses_short_token_plain_text(tmp_path):
    # Symbol shorter than min_symbol_length suppressed in plain-text mode.
    old = "def run(x): pass\n"
    new = "def run(x, y): pass\n"
    readme = "Please run the tool.\n"  # "run" as plain text (no backtick)

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        noise_blocklist=[],  # disable blocklist so only min_symbol_length applies
        min_symbol_length=4,
    )
    assert result.passed  # "run" is 3 chars < 4


def test_min_symbol_length_allows_backtick_match_for_short_token(tmp_path):
    # Same short symbol inside backticks should still fire.
    old = "def run(x): pass\n"
    new = "def run(x, y): pass\n"
    readme = "Call `run` to start.\n"

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        noise_blocklist=[],
        min_symbol_length=4,
    )
    assert result.failed


def test_custom_noise_blocklist_replaces_default(tmp_path):
    # Provide a custom blocklist that does NOT contain "build".
    # Plain-text "build" should then fire normally.
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "The build step is important.\n"

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
        noise_blocklist=["irrelevant_word"],  # custom list, "build" not in it
    )
    assert result.failed  # plain-text match fires because "build" not suppressed


def test_empty_noise_blocklist_disables_suppression(tmp_path):
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "The build step runs webpack.\n"

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
        noise_blocklist=[],
    )
    assert result.failed  # plain-text match fires with blocklist disabled


# --- key-path matching in README ---


def test_key_path_match_in_readme(tmp_path):
    # README mentions the full path "scripts.build" rather than bare "build".
    old = '{"scripts": {"build": "webpack"}}\n'
    new = '{"scripts": {"bundle": "webpack"}}\n'
    readme = "Defined in `scripts.build` inside package.json.\n"

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        is_config=True,
        filename="package.json",
    )
    assert result.failed
    assert any(f.symbol == "build" for f in result.findings)


def test_key_paths_populated_on_symbol_change(tmp_path):
    from readme_drift.config_diff import diff_config

    old = '{"scripts": {"build": "webpack"}}'
    new = '{"scripts": {"bundle": "webpack"}}'
    changes = diff_config(old, new, file="package.json")
    removed = [c for c in changes if c.name == "build"]
    assert removed, "expected a REMOVED change for 'build'"
    assert any("scripts.build" in kp for kp in removed[0].key_paths)


# --- verbose log ---


def test_verbose_log_populated(tmp_path):
    old = "def helper(x): pass\n"
    new = "def helper(x, y): pass\n"
    readme = "Use `helper` to process.\n"

    result = _run_pipeline_direct(old, new, readme, tmp_path, verbose=True)
    assert result.verbose_log, "verbose_log should be non-empty"
    combined = "\n".join(result.verbose_log)
    assert "helper" in combined


def test_verbose_log_shows_denied_symbol(tmp_path):
    old = "def helper(x): pass\n"
    new = "def helper(x, y): pass\n"
    readme = "Use `helper`.\n"

    result = _run_pipeline_direct(
        old,
        new,
        readme,
        tmp_path,
        symbol_denylist=["helper"],
        verbose=True,
    )
    combined = "\n".join(result.verbose_log)
    assert "helper" in combined
    assert "denied" in combined


# --- _symbols_from_changes includes key_paths ---


def test_symbols_from_changes_includes_key_paths():
    change = SymbolChange(
        name="build",
        change_type=ChangeType.REMOVED,
        key_paths=["scripts.build", "devScripts.build"],
    )
    symbols = _symbols_from_changes([change])
    assert "build" in symbols
    assert "scripts.build" in symbols
    assert "devScripts.build" in symbols


# --- default noise blocklist sanity ---


def test_default_noise_blocklist_contains_expected_words():
    for word in ("build", "test", "name", "version", "run"):
        assert word in _DEFAULT_NOISE_BLOCKLIST


# --- run_check integration (mocked git layer) ---


def _make_git_diff(py_files=None, cfg_files=None):
    from readme_drift.models import GitDiffResult

    return GitDiffResult(
        changed_py_files=py_files or [],
        changed_config_files=cfg_files or [],
    )


def test_run_check_skips_when_no_readme(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.find_readmes", return_value=[]),
    ):
        result = run_check(repo_root=tmp_path)

    assert result.skipped
    assert "no README" in result.skip_reason


def test_run_check_skips_when_no_relevant_files_changed(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    readme = tmp_path / "README.md"
    readme.write_text("# Hello")

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.find_readmes", return_value=[readme]),
        patch("readme_drift.drift_checker.get_diff", return_value=_make_git_diff()),
    ):
        result = run_check(repo_root=tmp_path)

    assert result.skipped
    assert "no Python or config files changed" in result.skip_reason


def test_run_check_returns_no_findings_when_no_symbol_changes(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    readme = tmp_path / "README.md"
    readme.write_text("# Hello world")
    py_file = tmp_path / "src.py"

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.find_readmes", return_value=[readme]),
        patch(
            "readme_drift.drift_checker.get_diff",
            return_value=_make_git_diff(py_files=[py_file]),
        ),
        patch(
            "readme_drift.drift_checker.read_old_content",
            return_value="def foo(): pass",
        ),
        patch(
            "readme_drift.drift_checker.read_new_content",
            return_value="def foo(): pass",
        ),
    ):
        result = run_check(repo_root=tmp_path)

    assert result.passed
    assert result.findings == []


def test_run_check_detects_removed_symbol_in_readme(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    readme = tmp_path / "README.md"
    readme.write_text("Call `connect` to connect.")
    py_file = tmp_path / "client.py"

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.find_readmes", return_value=[readme]),
        patch(
            "readme_drift.drift_checker.get_diff",
            return_value=_make_git_diff(py_files=[py_file]),
        ),
        patch(
            "readme_drift.drift_checker.read_old_content",
            return_value="def connect(): pass",
        ),
        patch("readme_drift.drift_checker.read_new_content", return_value=""),
    ):
        result = run_check(repo_root=tmp_path)

    assert result.failed
    assert any(f.symbol == "connect" for f in result.findings)


def test_run_check_exclude_filters_source_file(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    readme = tmp_path / "README.md"
    readme.write_text("Call `connect` to connect.")
    py_file = Path("generated/client.py")

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.find_readmes", return_value=[readme]),
        patch(
            "readme_drift.drift_checker.get_diff",
            return_value=_make_git_diff(py_files=[py_file]),
        ),
    ):
        result = run_check(repo_root=tmp_path, exclude=["generated/"])

    assert result.passed


def test_run_check_readme_paths_overrides_discovery(tmp_path):
    from unittest.mock import patch
    from readme_drift.drift_checker import run_check

    custom_readme = tmp_path / "CUSTOM.md"
    custom_readme.write_text("Call `connect`.")

    with (
        patch("readme_drift.drift_checker.validate_repo_root", return_value=tmp_path),
        patch("readme_drift.drift_checker.get_diff", return_value=_make_git_diff()),
    ):
        result = run_check(repo_root=tmp_path, readme_paths=[str(custom_readme)])

    assert result.skipped
