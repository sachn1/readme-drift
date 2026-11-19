"""Find README commands that were broken at a commit's parent and fixed or broken by that commit."""

import argparse
import json
from pathlib import Path

import run_benchmark as rb


def _key(row: dict) -> tuple[str, str]:
    """Identify a verified command by its text and README file."""
    return (row["raw"], row["file"])


def _status_at(repo: Path, rev: str) -> list[dict]:
    """Check out a revision and return its --verify rows."""
    rb._reset(repo)
    rb._git(repo, "checkout", "-qf", rev)
    return rb._verify_rows(repo)[0]


def _episodes_for(repo: Path, limit: int) -> tuple[list[dict], int]:
    """Return the episodes found in one repository and how many README commits were checked."""
    shas = rb._git(
        repo,
        "log",
        "--no-merges",
        "-n",
        str(limit),
        "--format=%H",
        "--",
        "*README*",
        "*readme*",
    ).split()
    found: list[dict] = []
    checked = 0
    for sha in shas:
        parents = rb._git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if not parents:
            continue
        try:
            before, after = _status_at(repo, parents[0]), _status_at(repo, sha)
        except Exception:  # noqa: BLE001 - a commit that cannot be checked is skipped
            continue
        checked += 1
        broken_before = {_key(r): r for r in before if r["status"] == "broken"}
        broken_after = {_key(r): r for r in after if r["status"] == "broken"}
        statuses: dict[tuple[str, str], set[str]] = {}
        for row in after:
            statuses.setdefault(_key(row), set()).add(row["status"])
        subject = rb._git(repo, "log", "-1", "--format=%s", sha)[:90]
        base = {"repo": repo.name, "sha": sha[:9], "subject": subject}
        for key, row in broken_before.items():
            if key not in broken_after:
                now = (
                    "verified"
                    if "verified" in statuses.get(key, set())
                    else (
                        "unverifiable"
                        if key in statuses
                        else "command removed or changed"
                    )
                )
                found.append(
                    {
                        **base,
                        "kind": "fixed",
                        "file": row["file"],
                        "command": row["raw"],
                        "reason": row["reason"],
                        "after": now,
                    }
                )
        for key, row in broken_after.items():
            if key not in broken_before:
                found.append(
                    {
                        **base,
                        "kind": "introduced",
                        "file": row["file"],
                        "command": row["raw"],
                        "reason": row["reason"],
                        "after": "broken",
                    }
                )
    return found, checked


def main() -> None:
    """Mine README-touching commits in every cloned repository and write the episodes as JSON.

    Returns
    -------
    None
        Episodes are written to ``--out``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos", type=Path, required=True, help="directory holding the clones"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, default=120, help="README-touching commits per repository"
    )
    args = parser.parse_args()
    episodes: list[dict] = []
    for repo in sorted(p for p in args.repos.iterdir() if (p / ".git").exists()):
        head = rb._git(repo, "rev-parse", "HEAD")
        try:
            found, checked = _episodes_for(repo, args.limit)
        finally:
            rb._reset(repo)
            rb._git(repo, "checkout", "-qf", head)
        episodes.extend(found)
        print(
            f"{repo.name:48} README commits checked: {checked:3}  episodes: {len(found)}",
            flush=True,
        )
    args.out.write_text(json.dumps(episodes, indent=1), encoding="utf-8")
    print(f"total episodes: {len(episodes)}")


if __name__ == "__main__":
    main()
