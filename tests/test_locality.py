"""A README in a subfolder is checked against changes in its own folder; the root README is global."""

import subprocess
from pathlib import Path

from readme_drift.drift_checker import run_check

COMPOSE_A = (
    "services:\n  web:\n    ports:\n      - '80:80'\n    volumes:\n      - x:/x\n"
)
COMPOSE_A_AFTER = "services:\n  web:\n    image: web\n"
FENCED_PORTS = "```yaml\nservices:\n  web:\n    ports:\n      - '80:80'\n```\n"


def _git(root: Path, *args: str) -> None:
    """Run a git command in a directory, failing the test on error."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path, before: dict[str, str], after: dict[str, str]):
    """Commit the before files, apply the after files, and return the check result."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    for rel, text in before.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "initial")
    for rel, text in after.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return run_check(base_ref="HEAD", repo_root=root)


def _flagged(result) -> set[str]:
    """Return the names of the flagged symbols."""
    return {f.change.name for f in result.findings}


def _where(result) -> set[str]:
    """Return the README paths that were matched, relative to nothing but their last two parts."""
    return {
        "/".join(m.readme_path.parts[-2:])
        for f in result.findings
        for m in f.readme_matches
    }


def test_nested_readme_ignores_a_change_in_a_sibling_folder(tmp_path):
    """A sibling service's README is not checked against another service's compose file."""
    result = _repo(
        tmp_path,
        {"a/compose.yaml": COMPOSE_A, "b/README.md": FENCED_PORTS},
        {"a/compose.yaml": COMPOSE_A_AFTER},
    )
    assert "ports" not in _flagged(result)


def test_nested_readme_is_checked_against_changes_in_its_own_folder(tmp_path):
    """The same key matches when the README sits next to the changed file."""
    result = _repo(
        tmp_path,
        {"a/compose.yaml": COMPOSE_A, "a/README.md": FENCED_PORTS},
        {"a/compose.yaml": COMPOSE_A_AFTER},
    )
    assert "ports" in _flagged(result)
    assert _where(result) == {"a/README.md"}


def test_nested_readme_is_checked_against_changes_deeper_in_its_folder(tmp_path):
    """A README covers its whole subtree, not only the files beside it."""
    result = _repo(
        tmp_path,
        {"a/sub/compose.yaml": COMPOSE_A, "a/README.md": FENCED_PORTS},
        {"a/sub/compose.yaml": COMPOSE_A_AFTER},
    )
    assert "ports" in _flagged(result)


def test_root_readme_is_global(tmp_path):
    """The root README is checked against changes anywhere in the repository."""
    result = _repo(
        tmp_path,
        {"a/compose.yaml": COMPOSE_A, "README.md": FENCED_PORTS},
        {"a/compose.yaml": COMPOSE_A_AFTER},
    )
    assert "ports" in _flagged(result)
    assert _where(result) == {tmp_path.name + "/README.md"}


def test_nested_readme_still_fires_on_an_exact_backtick_reference_elsewhere(tmp_path):
    """A distinctive name in a backtick span is stale wherever the change happened."""
    result = _repo(
        tmp_path,
        {
            ".github/ci.yaml": "env:\n  PROJECT_ID: x\n",
            "deploy/README.md": "Set `PROJECT_ID` before you deploy.\n",
        },
        {".github/ci.yaml": "env:\n  OTHER: x\n"},
    )
    assert "PROJECT_ID" in _flagged(result)


def test_nested_readme_ignores_plain_prose_mentions_from_elsewhere(tmp_path):
    """Plain prose in a nested README does not count for a change outside its folder."""
    result = _repo(
        tmp_path,
        {
            "a/app.py": "def connect_database():\n    pass\n",
            "b/README.md": "Call connect_database to start.\n",
        },
        {"a/app.py": "x = 1\n"},
    )
    assert "connect_database" not in _flagged(result)


def test_nested_readme_ignores_a_backticked_noise_word_from_elsewhere(tmp_path):
    """A backticked everyday word is too weak to cross folders."""
    result = _repo(
        tmp_path,
        {
            ".github/ci.yaml": "build:\n  name: x\n",
            "deploy/README.md": "The `name` field is required.\n",
        },
        {".github/ci.yaml": "build:\n  title: x\n"},
    )
    assert "name" not in _flagged(result)


def test_nested_readme_ignores_a_short_backticked_name_from_elsewhere(tmp_path):
    """A name shorter than four characters is too weak to cross folders."""
    result = _repo(
        tmp_path,
        {
            "a/app.py": "def qux():\n    pass\n",
            "b/README.md": "Use `qux` here.\n",
        },
        {"a/app.py": "x = 1\n"},
    )
    assert "qux" not in _flagged(result)


def test_explicit_readme_paths_are_global(tmp_path):
    """README files named with readme_paths are checked against every change."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a/app.py").write_text("def connect_database():\n    pass\n")
    (tmp_path / "b/README.md").write_text("Call connect_database to start.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "initial")
    (tmp_path / "a/app.py").write_text("x = 1\n")
    result = run_check(
        base_ref="HEAD", repo_root=tmp_path, readme_paths=["b/README.md"]
    )
    assert "connect_database" in _flagged(result)


def test_verbose_log_explains_a_change_skipped_for_scope(tmp_path):
    """--verbose says when a name was mentioned only in READMEs of other folders."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a/app.py").write_text("def connect_database():\n    pass\n")
    (tmp_path / "b/README.md").write_text("Call connect_database to start.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "initial")
    (tmp_path / "a/app.py").write_text("x = 1\n")
    result = run_check(base_ref="HEAD", repo_root=tmp_path, verbose=True)
    assert any("other folders" in line for line in result.verbose_log)


def test_nested_readme_next_to_the_change_still_catches_a_python_rename(tmp_path):
    """The usual case keeps working: a service README and its own code."""
    result = _repo(
        tmp_path,
        {
            "svc/app.py": "def connect_database():\n    pass\n",
            "svc/README.md": "Call connect_database to start.\n",
        },
        {"svc/app.py": "x = 1\n"},
    )
    assert "connect_database" in _flagged(result)
