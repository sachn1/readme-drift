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
    ReadmeMatch,
    StalenessFinding,
    SymbolChange,
)
from .constants import DEFAULT_NOISE_BLOCKLIST
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
    symbol_allowlist: list[str] | None = None,
    symbol_denylist: list[str] | None = None,
    readme_paths: list[str] | None = None,
    readme_exclude_dirs: list[str] | None = None,
    min_symbol_length: int = 4,
    noise_blocklist: list[str] | None = None,
    verbose: bool = False,
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
        symbol_allowlist: Symbols to always flag when changed, even if not in README.
        symbol_denylist: Symbols to never flag, even if changed and in README.
        readme_paths: Explicit list of README file paths to scan (overrides discovery).
        readme_exclude_dirs: Extra directory names to skip during README discovery.
        min_symbol_length: Minimum symbol length for plain-text matching (default 4).
            Shorter symbols are still matched inside backtick spans.
        noise_blocklist: Replaces the built-in noise blocklist.  Pass an empty list
            to disable noise suppression entirely.  None → use built-in default.
        verbose: If True, populate DriftCheckResult.verbose_log with per-symbol outcomes.

    Returns:
        A DriftCheckResult describing findings.
    """
    _exclude = exclude or []
    _allowlist: set[str] = set(symbol_allowlist or [])
    _denylist: set[str] = set(symbol_denylist or [])
    # None → use built-in default; [] → disable blocklist
    _blocklist: frozenset[str] = (
        DEFAULT_NOISE_BLOCKLIST
        if noise_blocklist is None
        else frozenset(noise_blocklist)
    )

    root = validate_repo_root(repo_root) if repo_root is not None else get_repo_root()
    resolved_root = root.resolve(strict=True)

    # README discovery — explicit list overrides recursive search.
    if readme_paths:
        discovered = [
            Path(p) if not Path(p).is_absolute() else Path(p) for p in readme_paths
        ]
        discovered = [p if p.is_absolute() else root / p for p in discovered]
        discovered = [p for p in discovered if p.exists()]
    else:
        extra_skip = set(readme_exclude_dirs) if readme_exclude_dirs else None
        discovered = find_readmes(root, extra_skip_dirs=extra_skip)

    if not discovered:
        return DriftCheckResult(skipped=True, skip_reason="no README file found")

    diff = get_diff(base_ref=base_ref, repo_root=root, staged=staged)

    if not diff.changed_py_files and not diff.changed_config_files:
        return DriftCheckResult(
            skipped=True,
            skip_reason="no Python or config files changed",
            readme_paths=discovered,
        )

    py_files = [f for f in diff.changed_py_files if not _is_excluded(f, _exclude)]
    cfg_files = [f for f in diff.changed_config_files if not _is_excluded(f, _exclude)]

    old_ref = base_ref if not staged else "HEAD"

    # Collect all symbol changes.
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
        return DriftCheckResult(readme_paths=discovered)

    # -----------------------------------------------------------------------
    # Filtering: denylist, then noise suppression.
    # The allowlist overrides noise suppression but NOT the denylist.
    # Priority order (highest first): denylist > allowlist > noise suppression.
    # -----------------------------------------------------------------------
    vlog: list[str] = []

    denied_changes: list[SymbolChange] = []
    active_changes: list[SymbolChange] = []
    for change in all_changes:
        if change.name in _denylist:
            denied_changes.append(change)
        else:
            active_changes.append(change)

    # Symbols that are too short or on the blocklist get backtick-only matching
    # unless they are explicitly on the allowlist.
    force_backtick_only: set[str] = set()
    for change in active_changes:
        if change.name in _allowlist:
            continue  # allowlist bypasses noise suppression
        if change.name in _blocklist:
            force_backtick_only.add(change.name)
        elif plain_text and len(change.name) < min_symbol_length:
            force_backtick_only.add(change.name)

    # Build the full set of symbols to search: leaf names + full key-paths from
    # config changes (e.g. "build" and "scripts.build").
    symbols_to_search = _symbols_from_changes(active_changes)

    # Scan all READMEs, merging matches by symbol name.
    all_readme_matches: dict[str, list[ReadmeMatch]] = {}
    for readme_path in discovered:
        for symbol, matches in scan_readme_for_symbols(
            readme_path,
            symbols_to_search,
            plain_text=plain_text,
            force_backtick_only=force_backtick_only,
        ).items():
            all_readme_matches.setdefault(symbol, []).extend(matches)

    # Shadow scan: for symbols restricted to backtick-only matching, also
    # check under full plain-text search. This never changes findings — it
    # only detects the "silent miss" case: a noise-suppressed or too-short
    # symbol with no backtick match, but a plain-text mention that would
    # have been caught had noise suppression not applied. Surfaced via
    # --verbose and the passing-run hint so un-backticked prose references
    # don't go unnoticed.
    plain_text_shadow_matches: dict[str, list[ReadmeMatch]] = {}
    if force_backtick_only:
        for readme_path in discovered:
            for symbol, matches in scan_readme_for_symbols(
                readme_path,
                list(force_backtick_only),
                plain_text=True,
                force_backtick_only=None,
            ).items():
                plain_text_shadow_matches.setdefault(symbol, []).extend(matches)

    # -----------------------------------------------------------------------
    # Build findings.
    # -----------------------------------------------------------------------
    findings: list[StalenessFinding] = []
    silently_missed_symbols: set[str] = set()

    for change in active_changes:
        if change.change_type == ChangeType.ADDED:
            if verbose:
                vlog.append(
                    f"{change.name} [{change.change_type.value}] → "
                    "additions are never stale → skipped"
                )
            continue

        # Collect README matches: leaf name + any matching key-path aliases.
        readme_matches: list[ReadmeMatch] = list(
            all_readme_matches.get(change.name, [])
        )
        for kp in change.key_paths:
            readme_matches.extend(all_readme_matches.get(kp, []))
        # Deduplicate by (readme_path, line_number) to avoid double-reporting
        # when both the leaf "build" and the path "scripts.build" appear.
        seen: set[tuple[Path, int]] = set()
        deduped: list[ReadmeMatch] = []
        for m in readme_matches:
            key = (m.readme_path, m.line_number)
            if key not in seen:
                seen.add(key)
                deduped.append(m)
        readme_matches = deduped

        in_readme = bool(readme_matches)
        on_allowlist = change.name in _allowlist
        suppressed = change.name in force_backtick_only and not in_readme
        silently_missed = suppressed and change.name in plain_text_shadow_matches
        if silently_missed:
            silently_missed_symbols.add(change.name)

        if on_allowlist and not in_readme:
            # Force-flag: symbol is critical; flag even without a README match.
            findings.append(StalenessFinding(change=change, readme_matches=[]))
            if verbose:
                vlog.append(
                    f"{change.name} [{change.change_type.value}] → "
                    "not found in README but on allowlist → FORCE-FLAGGED"
                )
        elif in_readme:
            findings.append(
                StalenessFinding(change=change, readme_matches=readme_matches)
            )
            if verbose:
                locations = ", ".join(
                    f"{m.readme_path.name}:{m.line_number}" for m in readme_matches
                )
                vlog.append(
                    f"{change.name} [{change.change_type.value}] → "
                    f"found at {locations} → FLAGGED"
                )
        else:
            if verbose:
                if silently_missed:
                    reason = (
                        "suppressed (noise filter) — matches README as plain "
                        "text; wrap in backticks or use --symbol-allowlist to "
                        "catch this"
                    )
                elif suppressed:
                    reason = "suppressed (noise filter, no backtick match)"
                else:
                    reason = "not found in any README"
                vlog.append(
                    f"{change.name} [{change.change_type.value}] → {reason} → skipped"
                )

    if verbose:
        for change in denied_changes:
            vlog.append(
                f"{change.name} [{change.change_type.value}] → on denylist → skipped"
            )

    return DriftCheckResult(
        findings=findings,
        readme_paths=discovered,
        verbose_log=vlog,
        suppressed_hint_count=len(silently_missed_symbols),
    )


def _symbols_from_changes(changes: list[SymbolChange]) -> list[str]:
    """Extract all symbol names (and key-path aliases) to search for in README."""
    names: set[str] = set()
    for change in changes:
        names.add(change.name)
        names.update(change.key_paths)
    return list(names)
