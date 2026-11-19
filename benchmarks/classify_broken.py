"""Re-judge broken --verify path results by whether the path ever existed and where it is now."""

import argparse
import re
import subprocess
from collections import Counter
from pathlib import Path

import triage


def _git(repo: Path, *args: str) -> str:
    """Run a read-only git command in a repository and return its stripped stdout."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120
    )
    return proc.stdout.strip()


def _classify(repo: Path, readme_file: str, reason: str) -> str:
    """Return how a broken path result should be treated under the history-aware rule."""
    match = re.search(r"path '([^']+)' does not exist", reason)
    if not match:
        return "other kind"
    path = match.group(1).lstrip("./")
    if not _git(
        repo, "log", "--all", "-n", "1", "--format=%h", "--", path, "*/" + path
    ):
        return "never existed: unverifiable"
    readme_dir = str(Path(readme_file).parent)
    prefix = "" if readme_dir == "." else readme_dir + "/"
    base = path.split("/")[-1]
    under = [
        f
        for f in _git(repo, "ls-files", "--", prefix + "*" + base).split()
        if f == prefix + path or f.endswith("/" + path)
    ]
    return (
        "exists under the README folder: unverifiable"
        if under
        else "BROKEN: existed before and is gone"
    )


def main() -> None:
    """Count how the history-aware rule would reclassify every broken path result.

    Returns
    -------
    None
        A summary is printed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        metavar=("RESULTS", "CLONES"),
        required=True,
        help="a results directory and the directory of clones it was run on",
    )
    args = parser.parse_args()
    counts: Counter = Counter()
    kept: list[str] = []
    for results, clones in args.pair:
        for record in triage.load(Path(results)):
            repo = Path(clones) / record["repo"].replace("/", "__")
            if not (repo / ".git").exists():
                continue
            for check in record["verify"].get("checks", []):
                if check["status"] != "broken":
                    continue
                verdict = _classify(repo, check["file"], check["reason"])
                counts[verdict] += 1
                if verdict.startswith("BROKEN"):
                    kept.append(
                        f"{record['repo']}  {check['file']}:{check['line']}  {check['raw'][:60]}"
                    )
    print(f"broken results examined: {sum(counts.values())}")
    for verdict, n in counts.most_common():
        print(f"  {n:4}  {verdict}")
    print("\n".join(kept))


if __name__ == "__main__":
    main()
