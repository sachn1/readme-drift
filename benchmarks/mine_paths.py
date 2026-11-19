"""Find commits that delete or rename a file whose path a README still mentions afterwards."""

import argparse
import json
import subprocess
from pathlib import Path

_IGNORED_SUFFIXES = (".md", ".rst", ".png", ".svg", ".jpg", ".gif", ".lock", ".sum")


def _git(repo: Path, *args: str) -> str:
    """Run a read-only git command in a repository and return its stdout."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=180
    )
    return proc.stdout


def _removed_paths(repo: Path, parent: str, sha: str) -> list[str]:
    """Return the old paths of files a commit deleted or renamed, minus docs and binaries."""
    paths = []
    for line in _git(repo, "diff", "--name-status", "-M70%", parent, sha).splitlines():
        parts = line.split("\t")
        if parts[0] == "D" or parts[0].startswith("R"):
            paths.append(parts[1])
    return [
        p
        for p in paths
        if "." in Path(p).name and not p.lower().endswith(_IGNORED_SUFFIXES)
    ]


def _episodes(repo: Path, limit: int) -> tuple[list[dict], int]:
    """Return stale-path episodes for one repository and how many commits moved files."""
    found: list[dict] = []
    moved = 0
    for sha in _git(
        repo, "log", "--no-merges", "-n", str(limit), "--format=%H"
    ).split():
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if not parents:
            continue
        probe = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", parents[0]], capture_output=True
        )
        if probe.returncode != 0:
            continue
        removed = _removed_paths(repo, parents[0], sha)
        if not removed:
            continue
        moved += 1
        subject = _git(repo, "log", "-1", "--format=%s", sha).strip()[:70]
        for old in removed[:60]:
            mentioned = _git(
                repo, "grep", "-lF", "-e", old, sha, "--", "*README*", "*readme*"
            ).split()
            if mentioned:
                found.append(
                    {
                        "repo": repo.name,
                        "sha": sha[:9],
                        "subject": subject,
                        "old_path": old,
                        "readme": mentioned[0].split(":", 1)[-1],
                    }
                )
    return found, moved


def main() -> None:
    """Report, per repository, commits that left a README pointing at a removed path.

    Returns
    -------
    None
        Episodes are written to ``--out`` as JSON.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos",
        type=Path,
        required=True,
        help="directory holding the clones (read-only)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, default=150, help="commits examined per repository"
    )
    args = parser.parse_args()
    episodes: list[dict] = []
    for repo in sorted(p for p in args.repos.iterdir() if (p / ".git").exists()):
        found, moved = _episodes(repo, args.limit)
        episodes.extend(found)
        print(
            f"{repo.name:48} commits moving files: {moved:4}  stale path mentions: {len(found)}",
            flush=True,
        )
    args.out.write_text(json.dumps(episodes, indent=1), encoding="utf-8")
    print(f"total stale path mentions: {len(episodes)}")


if __name__ == "__main__":
    main()
