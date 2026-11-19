"""Git utilities for extracting diffs and checking file changes."""

import subprocess
from pathlib import Path

from .config_diff import CONFIG_FILENAMES, CONFIG_SUFFIXES, LOCKFILE_NAMES
from .constants import README_NAMES as _README_NAMES, README_SKIP_DIRS as _SKIP_DIRS
from .models import GitDiffResult


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return its output, raising an error if it fails."""
    assert cmd, "cmd must not be empty"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=30
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out: {' '.join(cmd)}")
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def get_repo_root() -> Path:
    """Return the root directory of the current git repository.

    Returns
    -------
    Path
        Top-level directory reported by ``git rev-parse --show-toplevel``.

    Raises
    ------
    RuntimeError
        If the current directory is not inside a git repository.
    """
    root = _run(["git", "rev-parse", "--show-toplevel"])
    return Path(root)


def validate_repo_root(path: Path) -> Path:
    """Validate that a path is inside a git repository.

    Parameters
    ----------
    path : Path
        Candidate repository directory.

    Returns
    -------
    Path
        Top-level directory of the repository containing ``path``.

    Raises
    ------
    ValueError
        If ``path`` is not a directory or not inside a git repository.
    """
    if not path.is_dir():
        raise ValueError(f"repo_root is not a directory: {path}")
    try:
        actual = Path(_run(["git", "rev-parse", "--show-toplevel"], cwd=path))
    except RuntimeError as exc:
        raise ValueError(f"repo_root is not a git repository: {path}") from exc
    return actual


def read_new_content(
    py_file: Path, root: Path, resolved_root: Path, staged: bool
) -> str:
    """Return a file's current content from the working tree or the index.

    Parameters
    ----------
    py_file : Path
        File path relative to the repository root.
    root : Path
        Repository root.
    resolved_root : Path
        Fully resolved repository root, used to reject paths that escape it.
    staged : bool
        Read the staged version instead of the working-tree version.

    Returns
    -------
    str
        File content, or an empty string if the file is absent.
    """
    if staged:
        try:
            # 0 means "staged version" in git show syntax
            return _run(["git", "show", f":0:{py_file}"], cwd=root)
        except RuntimeError:
            return ""
    full_path = (root / py_file).resolve()
    assert full_path.is_relative_to(resolved_root), f"Path {py_file} escapes repo root"
    return full_path.read_text(encoding="utf-8") if full_path.exists() else ""


def read_old_content(py_file: Path, root: Path, old_ref: str) -> str:
    """Return a file's content at a git ref.

    Parameters
    ----------
    py_file : Path
        File path relative to the repository root.
    root : Path
        Repository root.
    old_ref : str
        Git ref to read from.

    Returns
    -------
    str
        File content at ``old_ref``, or an empty string if absent.
    """
    try:
        return _run(["git", "show", f"{old_ref}:{py_file}"], cwd=root)
    except RuntimeError:
        return ""


def get_diff(
    base_ref: str = "HEAD",
    repo_root: Path | None = None,
    staged: bool = False,
) -> GitDiffResult:
    """Get the files changed between the current state and a base ref.

    Parameters
    ----------
    base_ref : str, optional
        Git ref to diff against, by default "HEAD".
    repo_root : Path or None, optional
        Root of the git repository; auto-detected if None.
    staged : bool, optional
        Diff staged changes only (for pre-commit use), by default False.

    Returns
    -------
    GitDiffResult
        Changed Python files and changed config files.

    Raises
    ------
    ValueError
        If ``base_ref`` starts with ``-`` (would be parsed as a git flag).
    """
    assert base_ref, "base_ref must not be empty"

    # Prevents flag injection: a ref starting with '-' would be interpreted as a git flag.
    if base_ref.startswith("-"):
        raise ValueError(
            f"Invalid base_ref {base_ref!r}: git refs cannot start with '-'"
        )

    root = repo_root or get_repo_root()

    diff_args = ["git", "diff", "--name-only"]
    if staged:
        diff_args.append("--cached")
    else:
        diff_args.append(base_ref)

    changed_files_output = _run(diff_args, cwd=root)
    if not changed_files_output:
        return GitDiffResult(changed_py_files=[])

    changed_files = [Path(f) for f in changed_files_output.splitlines()]

    changed_py_files = [f for f in changed_files if f.suffix == ".py"]
    changed_config_files = [
        f
        for f in changed_files
        if (f.suffix.lower() in CONFIG_SUFFIXES or f.name in CONFIG_FILENAMES)
        and f.name not in LOCKFILE_NAMES
    ]

    return GitDiffResult(
        changed_py_files=changed_py_files,
        changed_config_files=changed_config_files,
    )


def find_readmes(
    repo_root: Path, extra_skip_dirs: set[str] | None = None
) -> list[Path]:
    """Find all README files in the repository, skipping dev-artifact directories.

    Parameters
    ----------
    repo_root : Path
        Directory to search recursively.
    extra_skip_dirs : set[str] or None, optional
        Additional directory names (not paths) to skip, merged with the built-in
        skip set. Mirrors the ``readme-exclude-dirs`` config key.

    Returns
    -------
    list[Path]
        Paths of all discovered README files.
    """
    skip = _SKIP_DIRS | (extra_skip_dirs or set())
    found = []
    queue = [repo_root]
    while queue:
        current = queue.pop()
        for path in current.iterdir():
            if path.is_symlink():
                continue
            if path.is_dir():
                if path.name not in skip:
                    queue.append(path)
            elif path.name.lower() in _README_NAMES:
                found.append(path)
    return found
