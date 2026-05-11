"""Git utilities for extracting diffs and checking file changes."""

import subprocess
from pathlib import Path

from .models import GitDiffResult

_README_EXTENSION_CANDIDATES = [".md", ".rst", ".txt", ""]
_readme_names = {f"readme{ext}" for ext in _README_EXTENSION_CANDIDATES}


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
    """Get the root directory of the git repository."""
    root = _run(["git", "rev-parse", "--show-toplevel"])
    return Path(root)


def _read_new_content(
    py_file: Path, root: Path, resolved_root: Path, staged: bool
) -> str:
    if staged:
        try:
            return _run(["git", "show", f":0:{py_file}"], cwd=root)
        except RuntimeError:
            return ""
    full_path = (root / py_file).resolve()
    assert full_path.is_relative_to(resolved_root), f"Path {py_file} escapes repo root"
    return full_path.read_text(encoding="utf-8") if full_path.exists() else ""


def _read_old_content(py_file: Path, root: Path, old_ref: str) -> str:
    try:
        return _run(["git", "show", f"{old_ref}:{py_file}"], cwd=root)
    except RuntimeError:
        return ""


def get_diff(
    base_ref: str = "HEAD",
    repo_root: Path | None = None,
    staged: bool = False,
) -> GitDiffResult:
    """Get changed files between current state and base_ref.

    Parameters
    ----------
    base_ref : str, optional
        Git ref to diff against (default: HEAD, i.e. last commit), by default "HEAD"
    repo_root : Path | None, optional
        Root of the git repository, by default None
    staged : bool, optional
        If True, diff staged changes only (for pre-commit use), by default False

    Returns
    -------
    GitDiffResult
        Result of the git diff operation.
    """
    assert base_ref, "base_ref must not be empty"
    if base_ref.startswith("-"):
        raise ValueError(
            f"Invalid base_ref {base_ref!r}: git refs cannot start with '-'"
        )

    root = repo_root or get_repo_root()
    resolved_root = root.resolve()

    diff_args = ["git", "diff", "--name-only"]
    if staged:
        diff_args.append("--cached")
    else:
        diff_args.append(base_ref)

    changed_files_output = _run(diff_args, cwd=root)
    if not changed_files_output:
        return GitDiffResult(changed_py_files=[], readme_changed=False)

    changed_files = [Path(f) for f in changed_files_output.splitlines()]

    readme_changed = any(f.name.lower() in _readme_names for f in changed_files)

    changed_py_files = [f for f in changed_files if f.suffix == ".py"]

    old_contents: dict[str, str] = {}
    new_contents: dict[str, str] = {}

    # When diffing vs a ref, old is that ref; in staged mode, old is HEAD.
    old_ref = base_ref if not staged else "HEAD"

    for py_file in changed_py_files:
        new_contents[str(py_file)] = _read_new_content(
            py_file, root, resolved_root, staged
        )
        old_contents[str(py_file)] = _read_old_content(py_file, root, old_ref)

    return GitDiffResult(
        changed_py_files=changed_py_files,
        readme_changed=readme_changed,
        old_file_contents=old_contents,
        new_file_contents=new_contents,
    )


def find_readmes(repo_root: Path) -> list[Path]:
    """Find all README files in the repository, excluding .git."""
    found = []
    queue = [repo_root]
    while queue:
        current = queue.pop()
        for path in current.iterdir():
            if path.is_dir():
                if path.name != ".git":
                    queue.append(path)
            elif path.name.lower() in _readme_names:
                found.append(path)
    return found
