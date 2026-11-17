"""Executable scenarios run end to end against the real tool."""

import subprocess

import pytest

from scenarios import SCENARIOS, VERIFY_SCENARIOS, run_scenario, run_verify_scenario

from readme_drift.drift_checker import run_check


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario(name, tmp_path):
    """Each documented scenario produces exactly the documented outcome."""
    *_, expected, hint = SCENARIOS[name]

    result = run_scenario(name, tmp_path)

    flagged = sorted(
        (f.change.name, f.change.change_type.value) for f in result.findings
    )
    assert flagged == expected
    assert result.suppressed_hint_count == hint


@pytest.mark.parametrize("name", VERIFY_SCENARIOS)
def test_verify_scenario(name, tmp_path):
    """Each --verify scenario yields exactly the documented checks, in README order."""
    *_, expected = VERIFY_SCENARIOS[name]

    result = run_verify_scenario(name, tmp_path)

    assert [(r.status.value, r.claim.raw) for r in result.results] == expected


def test_js_only_change_is_skipped(tmp_path):
    """A change to a non-Python, non-config file is skipped entirely."""

    def git(*args):
        """Run a git command in tmp_path, failing the test on error."""
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "a.js").write_text("function connect(){}\n")
    (tmp_path / "README.md").write_text("Call `connect()`.\n")
    git("add", ".")
    git("commit", "-qm", "initial")
    (tmp_path / "a.js").write_text("function open(){}\n")

    result = run_check(base_ref="HEAD", repo_root=tmp_path)

    assert result.skipped
    assert result.findings == []
