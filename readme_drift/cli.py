"""CLI entry point for readme-drift."""

import argparse
import sys
from pathlib import Path

from .checker import run_check
from .report import format_report


def main() -> None:
    """Parse arguments and run readme-drift."""
    parser = argparse.ArgumentParser(
        prog="readme-drift",
        description="Check if README may be stale after code changes.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD",
        help="Git ref to diff against (default: HEAD)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes only (use in pre-commit hooks)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Path to repo root (auto-detected if not set)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings but always exit 0 (non-blocking)",
    )

    args = parser.parse_args()

    result = run_check(
        base_ref=args.base_ref,
        repo_root=args.repo_root,
        staged=args.staged,
    )

    print(format_report(result))

    if result.failed and not args.warn_only:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
