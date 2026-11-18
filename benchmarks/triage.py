"""Label benchmark findings and compute the metrics shown in the analysis notebook."""

import json
import re
import statistics
from collections import Counter
from pathlib import Path

USEFUL = "useful"
FALSE_ALARM = "false-alarm"
UNLABELED = "unlabeled"

_CONFIG_SUFFIXES = (".toml", ".json", ".yml", ".yaml")

# Judgements made by reading the finding in context: (repo, symbol or command) -> (label, cause).
MANUAL: dict[tuple[str, str], tuple[str, str]] = {
    ("fastapi/fastapi", "Depends"): (USEFUL, "documented public API changed signature"),
    ("encode/httpx", "stream"): (USEFUL, "documented public API changed signature"),
    ("pallets/flask", "flask -A task_app run --debug"): (
        FALSE_ALARM,
        "flag-on-subcommand-not-readable",
    ),
    ("Textualize/rich", "python example.py"): (FALSE_ALARM, "illustrative-command"),
    ("fastapi/full-stack-fastapi-template", "docker compose up -d db mailpit"): (
        FALSE_ALARM,
        "compose-override-file-not-read",
    ),
    (
        "fastapi/full-stack-fastapi-template",
        "frontend/README.md::bash scripts/prestart.sh",
    ): (
        FALSE_ALARM,
        "runs-from-another-directory-named-in-prose",
    ),
}


def load(results_dir: Path) -> list[dict]:
    """Load every per-repository result file in a directory.

    Parameters
    ----------
    results_dir : Path
        Directory holding the JSON files written by the runner.

    Returns
    -------
    list[dict]
        One record per repository, sorted by name.
    """
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(results_dir.glob("*.json"))
    ]


def label_check(repo: str, check: dict) -> tuple[str, str]:
    """Label one broken ``--verify`` result as useful or a false alarm, with a cause.

    Parameters
    ----------
    repo : str
        Repository slug.
    check : dict
        A broken check row from the runner.

    Returns
    -------
    tuple[str, str]
        The label and a short cause.
    """
    manual = MANUAL.get((repo, f"{check['file']}::{check['raw']}")) or MANUAL.get(
        (repo, check["raw"])
    )
    if manual:
        return manual
    if check.get("found_next_to_readme"):
        return FALSE_ALARM, "nested-readme-resolution"
    return UNLABELED, "needs review"


def label_finding(repo: str, finding: dict) -> tuple[str, str]:
    """Label one diff-mode finding as useful or a false alarm, with a cause.

    Parameters
    ----------
    repo : str
        Repository slug.
    finding : dict
        A finding row from the runner (symbol, file, README matches, evidence).

    Returns
    -------
    tuple[str, str]
        The label and a short cause.
    """
    manual = MANUAL.get((repo, finding["symbol"]))
    if manual:
        return manual
    match = (
        finding["matches"][0] if finding["matches"] else {"text": "", "backtick": False}
    )
    text, symbol = match["text"], finding["symbol"]
    if (
        finding["file"].endswith(_CONFIG_SUFFIXES)
        or Path(finding["file"]).name == "Makefile"
    ):
        if finding.get("name_survives"):
            return FALSE_ALARM, "config-name-survives-migration"
        if not match["backtick"]:
            return FALSE_ALARM, "config-key-in-prose"
        return UNLABELED, "needs review"
    if text.lstrip().startswith((":::", ".. auto")):
        return FALSE_ALARM, "auto-generated-directive"
    if re.search(rf"`{re.escape(symbol)}[A-Za-z0-9_]", text):
        return FALSE_ALARM, "backtick-prefix"
    if not match["backtick"] and re.fullmatch(r"[a-z]+", symbol):
        return FALSE_ALARM, "common-word-in-prose"
    return UNLABELED, "needs review"


def md_table(headers: list[str], rows: list[list]) -> str:
    """Render rows as a GitHub-flavoured Markdown table.

    Parameters
    ----------
    headers : list[str]
        Column titles.
    rows : list[list]
        Row values; each is converted with ``str``.

    Returns
    -------
    str
        The Markdown table.
    """
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |"
        )
    return "\n".join(lines)


def show(markdown: str) -> None:
    """Display Markdown in a notebook, or print it as plain text elsewhere.

    Parameters
    ----------
    markdown : str
        Markdown text to display.
    """
    try:
        from IPython.display import Markdown, display

        display(Markdown(markdown))
    except ImportError:
        print(markdown)


def pct(part: int, whole: int) -> str:
    """Format a share as a percentage with its counts.

    Parameters
    ----------
    part : int
        Numerator.
    whole : int
        Denominator.

    Returns
    -------
    str
        For example ``67% (10/15)``, or ``n/a`` when ``whole`` is zero.
    """
    return f"{part * 100 // whole}% ({part}/{whole})" if whole else "n/a"


def metrics(records: list[dict]) -> dict:
    """Compute the headline numbers for one tool version across all repositories.

    Parameters
    ----------
    records : list[dict]
        Records returned by :func:`load`.

    Returns
    -------
    dict
        Counts and rates used for tables and before/after comparison.
    """
    out: Counter = Counter()
    seconds: list[float] = []
    for rec in records:
        repo = rec["repo"]
        for chk in rec.get("verify", {}).get("checks", []):
            out[f"verify_{chk['status']}"] += 1
            if chk["status"] == "broken":
                label, _ = label_check(repo, chk)
                out[f"verify_broken_{label}"] += 1
        for phase, prefix in (("replay", "diff"), ("replay_docs", "docs")):
            for commit in rec.get(phase, {}).get("commits", []):
                if "error" in commit:
                    out[f"{prefix}_errors"] += 1
                    continue
                out[f"{prefix}_commits"] += 1
                if prefix == "diff":
                    seconds.append(commit["seconds"])
                if commit["findings"]:
                    out[f"{prefix}_flagged_commits"] += 1
                for finding in commit["findings"]:
                    out[f"{prefix}_findings"] += 1
                    out[f"{prefix}_findings_{label_finding(repo, finding)[0]}"] += 1
        for inj in rec.get("inject", {}).get("injections", []):
            out["inject_total"] += 1
            caught = inj["detected"] or inj.get("verify_detected")
            out["inject_caught"] += bool(caught)
            out[f"inject_total_{inj['kind']}"] += 1
            out[f"inject_caught_{inj['kind']}"] += bool(caught)
    result = dict(out)
    if seconds:
        ordered = sorted(seconds)
        result["diff_seconds_median"] = round(statistics.median(ordered), 3)
        result["diff_seconds_p95"] = ordered[int(len(ordered) * 0.95)]
        result["diff_seconds_max"] = max(ordered)
    return result
