"""Tests for git utility helpers — README discovery."""

from pathlib import Path

import pytest

from readme_drift.git import find_readmes, validate_repo_root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("root readme")
    return tmp_path


def test_finds_root_readme(repo: Path):
    assert any(p.name == "README.md" for p in find_readmes(repo))


def test_finds_nested_readme(repo: Path):
    pkg = repo / "packages" / "core"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text("pkg readme")
    found = find_readmes(repo)
    assert len(found) == 2


def test_skips_git_dir(repo: Path):
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "README.md").write_text("should be ignored")
    found = find_readmes(repo)
    assert all(".git" not in str(p) for p in found)


def test_skips_node_modules(repo: Path):
    bad_readme = repo / "node_modules" / "some-pkg" / "README.md"
    bad_readme.parent.mkdir(parents=True)
    bad_readme.write_text("should be ignored")
    found = find_readmes(repo)
    assert bad_readme not in found


def test_skips_venv(repo: Path):
    bad_readme = repo / "venv" / "lib" / "README.md"
    bad_readme.parent.mkdir(parents=True)
    bad_readme.write_text("should be ignored")
    found = find_readmes(repo)
    assert bad_readme not in found


def test_skips_symlink_dirs(repo: Path):
    target = repo / "real_dir"
    target.mkdir()
    (target / "README.md").write_text("real")
    link = repo / "link_dir"
    link.symlink_to(target)
    found = find_readmes(repo)
    # Should find the README via real_dir but not traverse the symlink a second time
    names = [p.parent.name for p in found]
    assert names.count("real_dir") <= 1
    assert "link_dir" not in names


def test_finds_markdown_extension(repo: Path):
    (repo / "README.markdown").write_text("markdown readme")
    found = find_readmes(repo)
    extensions = {p.suffix for p in found}
    assert ".markdown" in extensions


def test_finds_rst_readme(repo: Path):
    (repo / "README.rst").write_text("rst readme")
    found = find_readmes(repo)
    extensions = {p.suffix for p in found}
    assert ".rst" in extensions


def test_case_insensitive_readme_name(repo: Path):
    (repo / "readme.md").write_text("lowercase")
    found = find_readmes(repo)
    assert any(p.name == "readme.md" for p in found)


def test_validate_repo_root_not_a_directory(tmp_path):
    with pytest.raises(ValueError, match="not a directory"):
        validate_repo_root(tmp_path / "nonexistent")


def test_validate_repo_root_not_a_git_repo(tmp_path):
    with pytest.raises(ValueError, match="not a git repository"):
        validate_repo_root(tmp_path)


def test_get_diff_rejects_dash_base_ref():
    from readme_drift.git import get_diff

    with pytest.raises(ValueError, match="cannot start with"):
        get_diff(base_ref="--evil")


def test_get_diff_classifies_makefile_as_config(tmp_path):
    import subprocess

    from readme_drift.git import get_diff

    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (tmp_path / "Makefile").write_text("build:\n\techo hi\n")
    run("add", "Makefile")
    run("commit", "-m", "init")

    (tmp_path / "Makefile").write_text("build:\n\techo hi\n\ndeploy:\n\techo deploy\n")
    run("add", "Makefile")

    diff = get_diff(staged=True, repo_root=tmp_path)
    assert Path("Makefile") in diff.changed_config_files
