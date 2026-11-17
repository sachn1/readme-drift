"""Tests for CLI helper functions: _load_toml_config, noise-allowlist resolution."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from readme_drift import messages
from readme_drift.cli import _load_toml_config, main, validate_options


# --- _load_toml_config ---


def test_load_toml_config_no_file(tmp_path, monkeypatch):
    """Load TOML config no file."""
    monkeypatch.chdir(tmp_path)  # do not pick up this repo's own pyproject.toml
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_no_section(tmp_path):
    """Load TOML config no section."""
    (tmp_path / "pyproject.toml").write_text("[tool.other]\nfoo = 1\n")
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_returns_section(tmp_path):
    """Load TOML config returns section."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.readme-drift]\nbase-ref = "main"\nwarn-only = true\n'
    )
    cfg = _load_toml_config(tmp_path)
    assert cfg == {"base-ref": "main", "warn-only": True}


def test_load_toml_config_invalid_toml_returns_empty(tmp_path):
    """Load TOML config invalid TOML returns empty."""
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe invalid")
    assert _load_toml_config(tmp_path) == {}


def test_load_toml_config_repo_root_takes_priority(tmp_path):
    """Load TOML config repo root takes priority."""
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
    """Load TOML config none falls back to cwd."""
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
    """Noise allowlist subtracts word from default."""
    kwargs = _invoke_main_with_mock(["--noise-allowlist", "run"])
    blocklist = kwargs["noise_blocklist"]
    assert blocklist is not None
    assert "run" not in blocklist
    assert "build" in blocklist  # other defaults preserved


def test_noise_allowlist_multiple_words():
    """Noise allowlist multiple words."""
    kwargs = _invoke_main_with_mock(
        ["--noise-allowlist", "run", "--noise-allowlist", "build"]
    )
    blocklist = kwargs["noise_blocklist"]
    assert "run" not in blocklist
    assert "build" not in blocklist
    assert "name" in blocklist  # unrelated default preserved


def test_noise_allowlist_ignored_when_noise_blocklist_set():
    """Noise allowlist ignored when noise blocklist set."""
    kwargs = _invoke_main_with_mock(
        ["--noise-blocklist", "custom", "--noise-allowlist", "run"]
    )
    assert kwargs["noise_blocklist"] == ["custom"]


def test_no_noise_flags_passes_none_to_run_check():
    """No noise flags passes none to run check."""
    kwargs = _invoke_main_with_mock([])
    assert kwargs["noise_blocklist"] is None


# --- --init -------------------------------------------------------------


def _init_repo(tmp_path):
    """Initialise an empty git repository in tmp_path."""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)


def test_init_creates_readme_when_absent(tmp_path):
    """--init creates README when absent."""
    _init_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--init", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    readme = tmp_path / "README.md"
    assert readme.exists()
    assert "backticks" in readme.read_text()


def test_init_refuses_to_overwrite_nonempty_readme(tmp_path):
    """--init refuses to overwrite nonempty README."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("# Existing content\n")
    runner = CliRunner()
    result = runner.invoke(main, ["--init", "--repo-root", str(tmp_path)])
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert (tmp_path / "README.md").read_text() == "# Existing content\n"


def test_init_overwrites_empty_readme(tmp_path):
    """--init overwrites empty README."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("   \n")
    runner = CliRunner()
    result = runner.invoke(main, ["--init", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "backticks" in (tmp_path / "README.md").read_text()


# --- validate_options ---------------------------------------------------


def _opts(**over):
    """Build keyword arguments for validate_options with overrides."""
    base = dict(
        readme_paths=(),
        readme_exclude_dirs=(),
        plain_text_search=True,
        noise_blocklist=(),
        noise_allowlist=(),
    )
    return {**base, **over}


def test_validate_options_clean_has_no_warnings():
    """Validate options clean has no warnings."""
    assert validate_options(**_opts()) == []


def test_validate_options_readme_paths_vs_exclude_dirs():
    """Validate options README paths vs exclude dirs."""
    out = validate_options(**_opts(readme_paths=("a",), readme_exclude_dirs=("b",)))
    assert out == [messages.WARN_READMEPATHS_EXCLUDEDIRS]


def test_validate_options_no_plain_text_with_noise_flags():
    """Validate options no plain text with noise flags."""
    out = validate_options(**_opts(plain_text_search=False, noise_allowlist=("run",)))
    assert out == [messages.WARN_NO_PLAIN_TEXT_NOISE]


def test_validate_options_blocklist_overrides_allowlist():
    """Validate options blocklist overrides allowlist."""
    out = validate_options(**_opts(noise_blocklist=("x",), noise_allowlist=("y",)))
    assert out == [messages.WARN_BLOCKLIST_OVERRIDES_ALLOWLIST]
