"""Main checker: orchestrates git diff → AST diff → README scan → report."""

import fnmatch
from pathlib import Path

from .ast_diff import diff_apis
from .config_diff import diff_config
from .git import (
    find_readmes,
    get_diff,
    get_repo_root,
    read_new_content,
    read_old_content,
    validate_repo_root,
)
from .models import (
    ChangeType,
    DriftCheckResult,
    GitDiffResult,
    ReadmeMatch,
    StalenessFinding,
    SymbolChange,
)
from .scanner import scan_readme_for_symbols


def _is_excluded(file: Path, exclude: list[str]) -> bool:
    """Return True if file matches any exclude pattern (glob or directory prefix)."""
    file_str = str(file)
    for pattern in exclude:
        if fnmatch.fnmatch(file_str, pattern) or fnmatch.fnmatch(file.name, pattern):
            return True
        if file_str.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def run_check(
    base_ref: str = "HEAD",
    repo_root: Path | None = None,
    staged: bool = False,
    include_private: bool = False,
    plain_text: bool = True,
    exclude: list[str] | None = None,
) -> DriftCheckResult:
    """
    Run the full README staleness check.

    Args:
        base_ref: Git ref to diff against.
        repo_root: Root of the repository. Auto-detected if not provided.
        staged: Check staged changes only (for pre-commit use).
        include_private: Include private (underscore-prefixed) symbols.
        plain_text: Match symbol names as plain text in addition to backtick spans.
        exclude: Glob patterns for files/directories to skip.

    Returns:
        A DriftCheckResult describing findings.
    """
    _exclude = exclude or []
    root = validate_repo_root(repo_root) if repo_root is not None else get_repo_root()
    resolved_root = root.resolve(strict=True)
    readme_paths = find_readmes(root)

    if not readme_paths:
        return DriftCheckResult(skipped=True, skip_reason="no README file found")

    diff: GitDiffResult = get_diff(base_ref=base_ref, repo_root=root, staged=staged)

    if not diff.changed_py_files and not diff.changed_config_files:
        return DriftCheckResult(
            skipped=True,
            skip_reason="no Python or config files changed",
            readme_paths=readme_paths,
        )

    py_files = [f for f in diff.changed_py_files if not _is_excluded(f, _exclude)]
    cfg_files = [f for f in diff.changed_config_files if not _is_excluded(f, _exclude)]

    old_ref = base_ref if not staged else "HEAD"

    # Collect all symbol changes — read content lazily, skipping excluded files
    all_changes: list[SymbolChange] = []
    for py_file in py_files:
        old_source = read_old_content(py_file, root, old_ref)
        new_source = read_new_content(py_file, root, resolved_root, staged)
        all_changes.extend(
            diff_apis(
                old_source,
                new_source,
                file=str(py_file),
                include_private=include_private,
            )
        )

    for cfg_file in cfg_files:
        old_source = read_old_content(cfg_file, root, old_ref)
        new_source = read_new_content(cfg_file, root, resolved_root, staged)
        all_changes.extend(diff_config(old_source, new_source, file=str(cfg_file)))

    if not all_changes:
        return DriftCheckResult(readme_paths=readme_paths)

    # Extract symbol names to search for in README
    symbols_to_search = _symbols_from_changes(all_changes)

    # Scan all READMEs and merge matches by symbol
    all_readme_matches: dict[str, list[ReadmeMatch]] = {}
    for readme_path in readme_paths:
        for symbol, matches in scan_readme_for_symbols(
            readme_path, symbols_to_search, plain_text=plain_text
        ).items():
            all_readme_matches.setdefault(symbol, []).extend(matches)

    # Build findings: only removals/sig-changes whose symbols appear in any README.
    # ADDED symbols are not stale — a README that already documents a new symbol is correct.
    findings: list[StalenessFinding] = []
    for change in all_changes:
        if change.change_type == ChangeType.ADDED:
            continue
        if change.name in all_readme_matches:
            findings.append(
                StalenessFinding(
                    change=change,
                    readme_matches=all_readme_matches[change.name],
                )
            )

    return DriftCheckResult(findings=findings, readme_paths=readme_paths)


def _symbols_from_changes(changes: list[SymbolChange]) -> list[str]:
    """Extract all symbol names that should be searched for in README."""
    return list({change.name for change in changes})
