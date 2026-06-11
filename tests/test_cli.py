"""Tests for CLI helper functions: _load_toml_config, noise-allowlist resolution."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from readme_drift.cli import _load_toml_config, main


# --- _load_toml_config ---


def test_load_toml_config_no_file(tmp_path):
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_no_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.other]\nfoo = 1\n")
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_returns_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.readme-drift]\nbase-ref = "main"\nwarn-only = true\n'
    )
    cfg = _load_toml_config(tmp_path)
    assert cfg == {"base-ref": "main", "warn-only": True}


def test_load_toml_config_invalid_toml_returns_empty(tmp_path):
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe invalid")
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_repo_root_takes_priority(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    (repo / "pyproject.toml").write_text(
        '[tool.readme-drift]\nbase-ref = "from-repo"\n'
    )
    (cwd / "pyproject.toml").write_text('[tool.readme-drift]\nbase-ref = "from-cwd"\n')

    cfg = _load_toml_config(repo)
    assert cfg["base-ref"] == "from-repo"


def test_load_toml_config_none_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.readme-drift]\nwarn-only = false\n")
    cfg = _load_toml_config(None)
    assert cfg == {"warn-only": False}


# --- noise-allowlist resolution ---


def _invoke_main_with_mock(args: list[str]) -> MagicMock:
    """Invoke main() with run_check mocked; return the mock call's kwargs."""
    mock_result = MagicMock(passed=True)
    with (
        patch("readme_drift.cli.run_check", return_value=mock_result) as mock_rc,
        patch("readme_drift.cli.format_report", return_value=""),
    ):
        runner = CliRunner()
        runner.invoke(main, args, catch_exceptions=False)
    return mock_rc.call_args.kwargs


def test_noise_allowlist_subtracts_word_from_default():
    kwargs = _invoke_main_with_mock(["--noise-allowlist", "run"])
    blocklist = kwargs["noise_blocklist"]
    assert blocklist is not None
    assert "run" not in blocklist
    assert "build" in blocklist  # other defaults preserved


def test_noise_allowlist_multiple_words():
    kwargs = _invoke_main_with_mock(
        ["--noise-allowlist", "run", "--noise-allowlist", "build"]
    )
    blocklist = kwargs["noise_blocklist"]
    assert "run" not in blocklist
    assert "build" not in blocklist
    assert "name" in blocklist  # unrelated default preserved


def test_noise_allowlist_ignored_when_noise_blocklist_set():
    kwargs = _invoke_main_with_mock(
        ["--noise-blocklist", "custom", "--noise-allowlist", "run"]
    )
    assert kwargs["noise_blocklist"] == ["custom"]


def test_no_noise_flags_passes_none_to_run_check():
    kwargs = _invoke_main_with_mock([])
    assert kwargs["noise_blocklist"] is None
