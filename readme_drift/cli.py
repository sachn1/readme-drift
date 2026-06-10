"""CLI entry point for readme-drift."""

import argparse
import sys
import tomllib
from pathlib import Path

from .drift_checker import run_check
from .report import format_report


def _load_toml_config(repo_root: Path | None) -> dict:
    """Read [tool.readme-drift] from pyproject.toml nearest to cwd or repo_root."""
    search_dirs = []
    if repo_root is not None:
        search_dirs.append(repo_root)
    search_dirs.append(Path.cwd())
    for directory in search_dirs:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            try:
                with candidate.open("rb") as f:
                    data = tomllib.load(f)
                return data.get("tool", {}).get("readme-drift", {})
            except Exception:
                return {}
    return {}


def _parse_bool(v: str) -> bool:
    if v.lower() in ("true", "1", "yes"):
        return True
    if v.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {v!r}")


def main() -> None:
    """Parse arguments and run readme-drift."""
    # Pre-parse --repo-root so we can locate pyproject.toml before setting defaults.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--repo-root", type=Path, default=None)
    known, _ = pre.parse_known_args()

    cfg = _load_toml_config(known.repo_root)

    parser = argparse.ArgumentParser(
        prog="readme-drift",
        description="Check if README may be stale after code changes.",
    )
    parser.add_argument(
        "--base-ref",
        default=cfg.get("base-ref", "HEAD"),
        help="Git ref to diff against (default: HEAD)",
    )
    parser.add_argument(
        "--staged",
        type=_parse_bool,
        nargs="?",
        const=True,
        default=cfg.get("staged", False),
        metavar="BOOL",
        help="Check staged changes only (use in pre-commit hooks, default: false)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Path to repo root (auto-detected if not set)",
    )
    parser.add_argument(
        "--include-private",
        type=_parse_bool,
        default=cfg.get("include-private", False),
        metavar="BOOL",
        help="Track private (underscore-prefixed) symbols too (default: false)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        metavar="PATTERN",
        default=list(cfg.get("exclude", [])),
        help="Glob pattern for files/directories to skip (repeatable)",
    )
    parser.add_argument(
        "--plain-text-search",
        type=_parse_bool,
        default=cfg.get("plain-text-search", True),
        metavar="BOOL",
        help="Match symbols as plain text in addition to backtick spans (default: true)",
    )
    parser.add_argument(
        "--warn-only",
        type=_parse_bool,
        default=cfg.get("warn-only", False),
        metavar="BOOL",
        help="Print warnings but always exit 0 (default: false)",
    )
    # --- v1.2.0 additions ---
    parser.add_argument(
        "--symbol-allowlist",
        action="append",
        metavar="SYMBOL",
        default=list(cfg.get("symbol-allowlist", [])),
        help=(
            "Symbol name to always flag when changed, even if not mentioned in the README "
            "(repeatable). Use for critical public API symbols."
        ),
    )
    parser.add_argument(
        "--symbol-denylist",
        action="append",
        metavar="SYMBOL",
        default=list(cfg.get("symbol-denylist", [])),
        help=(
            "Symbol name to never flag, even if changed and found in the README "
            "(repeatable). Overrides --symbol-allowlist."
        ),
    )
    parser.add_argument(
        "--readme-paths",
        action="append",
        metavar="PATH",
        default=list(cfg.get("readme-paths", [])),
        help=(
            "Explicit README file path to scan (repeatable). "
            "When provided, disables recursive README discovery."
        ),
    )
    parser.add_argument(
        "--readme-exclude-dirs",
        action="append",
        metavar="DIR",
        default=list(cfg.get("readme-exclude-dirs", [])),
        help="Directory name to skip during README discovery (repeatable).",
    )
    parser.add_argument(
        "--min-symbol-length",
        type=int,
        default=cfg.get("min-symbol-length", 4),
        metavar="N",
        help=(
            "Minimum symbol length for plain-text (word-boundary) matching. "
            "Shorter symbols are still matched inside backtick spans (default: 4)."
        ),
    )
    parser.add_argument(
        "--noise-blocklist",
        action="append",
        metavar="WORD",
        default=None,  # None → use built-in default; [] via config → disable
        help=(
            "Add a word to the noise blocklist, suppressing plain-text matches for it "
            "(repeatable). When provided via CLI, replaces the built-in default list."
        ),
    )
    parser.add_argument(
        "--verbose",
        type=_parse_bool,
        nargs="?",
        const=True,
        default=cfg.get("verbose", False),
        metavar="BOOL",
        help=(
            "Print per-symbol scan outcomes (flagged / skipped / suppressed) "
            "after the main report (default: false)."
        ),
    )

    args = parser.parse_args()

    # Resolve noise_blocklist: CLI takes precedence; fall back to config file value;
    # None means "use built-in default" inside run_check.
    noise_blocklist: list[str] | None
    if args.noise_blocklist is not None:
        # CLI flag(s) provided — use them as the complete blocklist.
        noise_blocklist = args.noise_blocklist
    elif "noise-blocklist" in cfg:
        # Config file key present (may be an empty list to disable).
        noise_blocklist = list(cfg["noise-blocklist"])
    else:
        noise_blocklist = None  # trigger built-in default inside run_check

    result = run_check(
        base_ref=args.base_ref,
        repo_root=args.repo_root,
        staged=args.staged,
        include_private=args.include_private,
        plain_text=args.plain_text_search,
        exclude=args.exclude,
        symbol_allowlist=args.symbol_allowlist or None,
        symbol_denylist=args.symbol_denylist or None,
        readme_paths=args.readme_paths or None,
        readme_exclude_dirs=args.readme_exclude_dirs or None,
        min_symbol_length=args.min_symbol_length,
        noise_blocklist=noise_blocklist,
        verbose=args.verbose,
    )

    print(format_report(result))

    if result.failed and not args.warn_only:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
