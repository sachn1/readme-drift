"""Main checker: orchestrates git diff → AST diff → README scan → report."""

from pathlib import Path

from .ast_diff import diff_apis
from .config_diff import diff_config
from .git import find_readmes, get_diff, get_repo_root
from .models import (
    ChangeType,
    CheckResult,
    GitDiffResult,
    ReadmeMatch,
    StalenessFinding,
    SymbolChange,
)
from .scanner import scan_readme_for_symbols


def run_check(
    base_ref: str = "HEAD",
    repo_root: Path | None = None,
    staged: bool = False,
) -> CheckResult:
    """
    Run the full README staleness check.

    Args:
        base_ref: Git ref to diff against.
        repo_root: Root of the repository. Auto-detected if not provided.
        staged: Check staged changes only (for pre-commit use).

    Returns:
        A CheckResult describing findings.
    """
    root = repo_root or get_repo_root()
    readme_paths = find_readmes(root)

    if not readme_paths:
        return CheckResult(skipped=True, skip_reason="no README file found")

    diff: GitDiffResult = get_diff(base_ref=base_ref, repo_root=root, staged=staged)

    if not diff.changed_py_files and not diff.changed_config_files:
        return CheckResult(
            skipped=True,
            skip_reason="no Python or config files changed",
            readme_paths=readme_paths,
        )

    # Collect all symbol changes across all changed Python files
    all_changes: list[SymbolChange] = []
    for py_file in diff.changed_py_files:
        key = str(py_file)
        old_source = diff.old_file_contents.get(key, "")
        new_source = diff.new_file_contents.get(key, "")
        all_changes.extend(diff_apis(old_source, new_source, file=key))

    # Collect key-path changes across all changed config files
    for cfg_file in diff.changed_config_files:
        key = str(cfg_file)
        old_source = diff.old_file_contents.get(key, "")
        new_source = diff.new_file_contents.get(key, "")
        all_changes.extend(diff_config(old_source, new_source, file=key))

    if not all_changes:
        return CheckResult(readme_paths=readme_paths)

    # Extract symbol names to search for in README
    symbols_to_search = _symbols_from_changes(all_changes)

    # Scan all READMEs and merge matches by symbol
    all_readme_matches: dict[str, list[ReadmeMatch]] = {}
    for readme_path in readme_paths:
        for symbol, matches in scan_readme_for_symbols(
            readme_path, symbols_to_search
        ).items():
            all_readme_matches.setdefault(symbol, []).extend(matches)

    # Build findings: only removals/renames/sig-changes whose symbols appear in any README.
    # ADDED symbols are not stale — a README that already documents a new symbol is correct.
    findings: list[StalenessFinding] = []
    for change in all_changes:
        if change.change_type == ChangeType.ADDED:
            continue
        relevant_name = _primary_name(change)
        if relevant_name in all_readme_matches:
            findings.append(
                StalenessFinding(
                    change=change,
                    readme_matches=all_readme_matches[relevant_name],
                )
            )

    return CheckResult(findings=findings, readme_paths=readme_paths)


def _symbols_from_changes(changes: list[SymbolChange]) -> list[str]:
    """Extract all symbol names that should be searched for in README."""
    symbols: set[str] = set()
    for change in changes:
        symbols.add(change.name)
        # For renames, also search for the old name (what the README still references)
        if change.change_type == ChangeType.RENAMED and change.old_signature:
            symbols.add(change.old_signature)
    return list(symbols)


def _primary_name(change: SymbolChange) -> str:
    """The symbol name most likely to appear in the README for this change."""
    if change.change_type == ChangeType.RENAMED:
        return change.old_signature or change.name
    return change.name
