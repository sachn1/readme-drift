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

    args = parser.parse_args()

    result = run_check(
        base_ref=args.base_ref,
        repo_root=args.repo_root,
        staged=args.staged,
        include_private=args.include_private,
        plain_text=args.plain_text_search,
        exclude=args.exclude,
    )

    print(format_report(result))

    if result.failed and not args.warn_only:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
