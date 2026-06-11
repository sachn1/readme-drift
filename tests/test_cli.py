"""Tests for CLI helper functions: _load_toml_config."""

from readme_drift.cli import _load_toml_config


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
