"""Tests for the one-time first-use backtick tip."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from readme_drift.cli import main
from readme_drift.tips import BACKTICK_TIP, first_use_tip, tips_disabled


def _env(tmp_path, **extra):
    return {"XDG_CACHE_HOME": str(tmp_path / "cache"), **extra}


def test_tip_shown_once_per_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = _env(tmp_path)
    assert first_use_tip(repo, passed=True, env=env) == BACKTICK_TIP
    assert first_use_tip(repo, passed=True, env=env) is None


def test_tip_is_per_repo(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    env = _env(tmp_path)
    assert first_use_tip(a, passed=True, env=env)
    assert first_use_tip(b, passed=True, env=env)


def test_tip_mentions_backticks_and_how_to_silence():
    assert "backticks" in BACKTICK_TIP
    assert "tips = false" in BACKTICK_TIP


def test_disabled_by_env_var(tmp_path):
    env = _env(tmp_path, README_DRIFT_NO_TIPS="1")
    assert tips_disabled({}, env)
    assert first_use_tip(tmp_path, passed=True, env=env) is None


def test_disabled_in_ci(tmp_path):
    assert first_use_tip(tmp_path, passed=True, env=_env(tmp_path, CI="true")) is None


def test_disabled_by_config(tmp_path):
    assert (
        first_use_tip(tmp_path, passed=True, cfg={"tips": False}, env=_env(tmp_path))
        is None
    )


def test_pre_commit_pass_does_not_consume_tip(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = _env(tmp_path, PRE_COMMIT="1")
    # Passing hook output is hidden by pre-commit: don't show, don't consume.
    assert first_use_tip(repo, passed=True, env=env) is None
    # First failing run is visible: tip appears.
    assert first_use_tip(repo, passed=False, env=env) == BACKTICK_TIP
    assert first_use_tip(repo, passed=False, env=env) is None


def test_unwritable_cache_skips_tip(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    env = {"XDG_CACHE_HOME": str(blocker)}  # a file, so mkdir fails
    assert first_use_tip(tmp_path, passed=True, env=env) is None


def test_cli_prints_tip_to_stderr_once(tmp_path, monkeypatch):
    monkeypatch.delenv("README_DRIFT_NO_TIPS")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PRE_COMMIT", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result_mock = MagicMock(passed=True)
    with (
        patch("readme_drift.cli.run_check", return_value=result_mock),
        patch("readme_drift.cli.format_report", return_value="report"),
        patch("readme_drift.cli.get_repo_root", return_value=tmp_path),
    ):
        runner = CliRunner()
        first = runner.invoke(main, [])
        second = runner.invoke(main, [])
    assert "backticks" in first.stderr
    assert "backticks" not in first.stdout
    assert "backticks" not in second.stderr
