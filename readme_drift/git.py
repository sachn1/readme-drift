"""Git utilities for extracting diffs and checking file changes."""

import subprocess
from pathlib import Path

from .config_diff import CONFIG_SUFFIXES
from .models import GitDiffResult

_readme_extension_candidates = [".md", ".markdown", ".rst", ".txt", ""]
_README_NAMES = {f"readme{ext}" for ext in _readme_extension_candidates}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    ".tox",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
}


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


def validate_repo_root(path: Path) -> Path:
    """Validate that path is a git repository; raise ValueError if not."""
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
    """Return file content from disk (working tree) or the staging area."""
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
    """Return file content at old_ref from git history; empty string if absent."""
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
        f for f in changed_files if f.suffix.lower() in CONFIG_SUFFIXES
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
    extra_skip_dirs:
        Additional directory *names* (not paths) to skip during traversal,
        merged with the built-in ``_SKIP_DIRS`` set.  Mirrors the
        ``readme-exclude-dirs`` config key.
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
