"""Run readme-drift against popular open-source repositories and record the results."""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import readme_drift
from readme_drift.constants import DEFAULT_NOISE_BLOCKLIST
from readme_drift.drift_checker import run_check
from readme_drift.git import find_readmes
from readme_drift.verify import run_verify

REPOS = [
    "psf/requests",
    "pallets/flask",
    "fastapi/fastapi",
    "fastapi/full-stack-fastapi-template",
    "pytest-dev/pytest",
    "encode/httpx",
    "Textualize/rich",
    "python-poetry/poetry",
    "pydantic/pydantic",
    "expressjs/express",
]
CLONE_DEPTH = 400
REPLAY_COMMITS = 150
HOOK_COMMITS = 4
INJECTIONS_PER_KIND = 6
_CODE_GLOBS = ["*.py", "*.toml", "*.yml", "*.yaml", "*.json", "Makefile"]
_TICK_RE = re.compile(r"`([A-Za-z_][\w.]*)(?:\([^`]*\))?`")
_COMPOSE_NAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def _git(repo: Path, *args: str, check: bool = True, stdin: str | None = None) -> str:
    """Run a git command in a repository and return its stripped stdout."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=300,
        input=stdin,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def _clone(slug: str, dest: Path) -> None:
    """Shallow-clone a GitHub repository unless it is already present."""
    if (dest / ".git").exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{slug}.git"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", str(CLONE_DEPTH), url, str(dest)],
        check=True,
        timeout=1800,
    )


def _reset(repo: Path) -> None:
    """Discard every working-tree and index change."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")


def _tool_info() -> dict:
    """Describe which readme-drift checkout is being measured."""
    root = Path(next(iter(readme_drift.__path__))).resolve().parent
    try:
        commit = _git(root, "rev-parse", "--short", "HEAD")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    except (RuntimeError, OSError):
        commit = branch = "unknown"
    return {"root": str(root), "commit": commit, "branch": branch}


def _check_rows(result) -> list[dict]:
    """Flatten a VerifyResult into JSON-friendly rows."""
    return [
        {
            "status": r.status.value,
            "raw": r.claim.raw,
            "head": r.claim.head,
            "file": str(r.claim.readme_path),
            "line": r.claim.line_number,
            "reason": r.reason,
        }
        for r in result.results
    ]


def _verify_rows(repo: Path) -> tuple[list[dict], float]:
    """Run --verify and return its rows (paths relative to the repo) and seconds."""
    started = time.perf_counter()
    result = run_verify(repo_root=repo)
    elapsed = round(time.perf_counter() - started, 3)
    rows = _check_rows(result)
    for row in rows:
        row["file"] = str(Path(row["file"]).relative_to(repo))
    return rows, elapsed


def _next_to_readme(repo: Path, row: dict) -> bool | None:
    """Return whether a 'missing' name exists beside the README that mentions it."""
    base = (repo / row["file"]).parent
    reason = row["reason"]
    if m := re.search(r"make target '([^']+)'", reason):
        for name in ("Makefile", "makefile", "GNUmakefile"):
            if (base / name).is_file():
                text = (base / name).read_text(encoding="utf-8", errors="ignore")
                return bool(re.search(rf"^{re.escape(m.group(1))}\s*:", text, re.M))
        return False
    if m := re.search(r"path '([^']+)' does not exist", reason):
        return (base / m.group(1)).exists()
    if m := re.search(r"script '([^']+)' not found in package.json", reason):
        pkg = base / "package.json"
        return pkg.is_file() and f'"{m.group(1)}"' in pkg.read_text(
            encoding="utf-8", errors="ignore"
        )
    if m := re.search(r"service '([^']+)' not found", reason):
        pattern = rf"^\s+{re.escape(m.group(1))}:"
        return any(
            (base / n).is_file()
            and re.search(
                pattern, (base / n).read_text(encoding="utf-8", errors="ignore"), re.M
            )
            for n in _COMPOSE_NAMES
        )
    return None


def _verify_phase(repo: Path) -> dict:
    """Run a full --verify scan and return every check with its outcome."""
    rows, elapsed = _verify_rows(repo)
    for row in rows:
        if row["status"] == "broken":
            row["nested_readme"] = (repo / row["file"]).parent != repo
            row["found_next_to_readme"] = _next_to_readme(repo, row)
    return {
        "seconds": elapsed,
        "readmes": [str(p.relative_to(repo)) for p in find_readmes(repo)],
        "checks": rows,
    }


def _name_survives(repo: Path, change) -> bool | None:
    """Return whether a removed config name still appears in the file's new text."""
    path = repo / change.file
    if (
        Path(change.file).suffix not in (".toml", ".json", ".yml", ".yaml")
        or not path.is_file()
    ):
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    return bool(re.search(rf"(?<![\w-]){re.escape(change.name)}(?![\w-])", text))


def _finding_rows(result, repo: Path) -> list[dict]:
    """Flatten diff-check findings into JSON-friendly rows."""
    return [
        {
            "name_survives": _name_survives(repo, f.change),
            "symbol": f.change.name,
            "type": f.change.change_type.value,
            "file": f.change.file,
            "matches": [
                {
                    "readme": str(m.readme_path.relative_to(repo)),
                    "line": m.line_number,
                    "text": m.line_text[:220],
                    "backtick": m.matched_text.startswith("`"),
                }
                for m in f.readme_matches[:3]
            ],
        }
        for f in result.findings
    ]


def _commit_pairs(repo: Path) -> list[tuple[str, str]]:
    """Return recent (commit, parent) pairs that touched code or config."""
    shas = _git(
        repo, "log", "--no-merges", "-n", "900", "--format=%H", "--", *_CODE_GLOBS
    ).split()
    pairs: list[tuple[str, str]] = []
    for sha in shas:
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if not parents:
            continue
        probe = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", parents[0]], capture_output=True
        )
        if probe.returncode == 0:
            pairs.append((sha, parents[0]))
        if len(pairs) >= REPLAY_COMMITS:
            break
    return pairs


def _stage_commit(repo: Path, sha: str, parent: str) -> list[str]:
    """Check out the parent and stage the commit's changes, like `git add` would."""
    _reset(repo)
    _git(repo, "checkout", "-qf", parent)
    patch = subprocess.run(
        ["git", "-C", str(repo), "diff", "--binary", parent, sha],
        capture_output=True,
        timeout=300,
    ).stdout
    applied = subprocess.run(
        ["git", "-C", str(repo), "apply", "--index", "--whitespace=nowarn", "-"],
        input=patch,
        capture_output=True,
        timeout=300,
    )
    if applied.returncode != 0:
        raise RuntimeError("patch did not apply")
    return _git(repo, "diff", "--cached", "--name-only").splitlines()


def _replay_phase(repo: Path, readme_paths: list[str] | None = None) -> dict:
    """Replay recent real commits through the hook's staged path."""
    head = _git(repo, "rev-parse", "HEAD")
    rows: list[dict] = []
    try:
        for sha, parent in _commit_pairs(repo):
            try:
                changed = _stage_commit(repo, sha, parent)
            except RuntimeError as exc:
                rows.append({"sha": sha[:10], "error": str(exc)})
                continue
            started = time.perf_counter()
            try:
                result = run_check(
                    staged=True, repo_root=repo, readme_paths=readme_paths
                )
            except Exception as exc:  # noqa: BLE001 - record and keep going
                rows.append({"sha": sha[:10], "error": repr(exc)[:200]})
                continue
            rows.append(
                {
                    "sha": sha[:10],
                    "subject": _git(repo, "log", "-1", "--format=%s", sha)[:100],
                    "seconds": round(time.perf_counter() - started, 3),
                    "skipped": result.skipped,
                    "readme_touched": any(
                        Path(f).name.lower().startswith("readme") for f in changed
                    ),
                    "suppressed_hint": result.suppressed_hint_count,
                    "findings": _finding_rows(result, repo),
                }
            )
    finally:
        _reset(repo)
        _git(repo, "checkout", "-qf", head)
    return {"commits": rows}


def _docs_files(repo: Path) -> list[str]:
    """Return Markdown and reStructuredText files under docs/ (English tree if split)."""
    root = repo / "docs" / "en" if (repo / "docs" / "en").exists() else repo / "docs"
    if not root.exists():
        return []
    found = sorted(p for p in root.rglob("*") if p.suffix in (".md", ".rst"))
    return [str(p.relative_to(repo)) for p in found[:400]]


def _replay_docs_phase(repo: Path) -> dict:
    """Replay the same commits while also scanning the docs/ folder, as a what-if."""
    docs = _docs_files(repo)
    if not docs:
        return {"commits": [], "docs_files": 0}
    readmes = [str(p.relative_to(repo)) for p in find_readmes(repo)]
    out = _replay_phase(repo, readme_paths=readmes + docs)
    out["docs_files"] = len(docs)
    return out


def _hook_phase(repo: Path, hook_repo: str, precommit_path: str) -> dict:
    """Run the real pre-commit framework hook on a few staged real commits."""
    if not precommit_path:
        return {"skipped": "no --precommit-path given"}
    head = _git(repo, "rev-parse", "HEAD")
    env = {**os.environ, "PYTHONPATH": precommit_path}
    rows: list[dict] = []
    try:
        for sha, parent in _commit_pairs(repo)[:HOOK_COMMITS]:
            try:
                _stage_commit(repo, sha, parent)
            except RuntimeError as exc:
                rows.append({"sha": sha[:10], "error": str(exc)})
                continue
            started = time.perf_counter()
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pre_commit",
                    "try-repo",
                    hook_repo,
                    "readme-drift",
                    "--verbose",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                env=env,
                timeout=900,
            )
            out = proc.stdout + proc.stderr
            status = (
                "failed"
                if proc.returncode == 1
                else "passed"
                if proc.returncode == 0
                else f"error-{proc.returncode}"
            )
            if "no files to check" in out.lower():
                status = "skipped-no-files"
            rows.append(
                {
                    "sha": sha[:10],
                    "status": status,
                    "seconds": round(time.perf_counter() - started, 2),
                    "tail": out.strip()[-300:],
                }
            )
    finally:
        _reset(repo)
        _git(repo, "checkout", "-qf", head)
    return {"runs": rows}


def _readme_text(repo: Path) -> str:
    """Return the concatenated text of every README in the repository."""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in find_readmes(repo)
    )


def _ref_styles(name: str, qualified: str, ticks: list[str]) -> list[str]:
    """Classify how READMEs refer to a symbol: bare, qualified or instance style."""
    styles = []
    for tick in ticks:
        parts = tick.split(".")
        if parts[-1] != name:
            continue
        if tick == name:
            styles.append("bare")
        elif tick == qualified:
            styles.append("qualified")
        elif len(parts) == 2 and parts[0][:1].islower():
            styles.append("instance")
    return sorted(set(styles))


def _python_candidates(repo: Path, readme: str) -> list[dict]:
    """Find public functions, classes and methods whose names a README mentions."""
    ticks = _TICK_RE.findall(readme)
    last = {t.split(".")[-1] for t in ticks}
    found: list[dict] = []
    for rel in _git(repo, "ls-files", "*.py").splitlines():
        if any(
            part in rel.split("/")
            for part in ("tests", "test", "docs", "docs_src", "examples")
        ):
            continue
        try:
            tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if not isinstance(
                node, (ast.FunctionDef, ast.ClassDef)
            ) or node.name.startswith("_"):
                continue
            if node.name in last:
                found.append(
                    {
                        "file": rel,
                        "name": node.name,
                        "symbol": node.name,
                        "line": node.lineno,
                        "node": type(node).__name__,
                        "styles": _ref_styles(node.name, node.name, ticks),
                    }
                )
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, ast.FunctionDef)
                        and not item.name.startswith("_")
                        and item.name in last
                    ):
                        qualified = f"{node.name}.{item.name}"
                        found.append(
                            {
                                "file": rel,
                                "name": item.name,
                                "symbol": qualified,
                                "line": item.lineno,
                                "node": "Method",
                                "styles": _ref_styles(item.name, qualified, ticks),
                            }
                        )
    per_file: dict[str, int] = {}
    picked: list[dict] = []
    for cand in sorted(found, key=lambda c: (c["file"], c["line"])):
        if per_file.get(cand["file"], 0) >= 1:
            continue
        per_file[cand["file"]] = 1
        picked.append(cand)
    return picked[: INJECTIONS_PER_KIND * 2]


def _detect(repo: Path, symbols: set[str], baseline_broken: set[str]) -> dict:
    """Stage the working tree and report whether diff mode and --verify noticed."""
    _git(repo, "add", "-A")
    started = time.perf_counter()
    result = run_check(staged=True, repo_root=repo)
    elapsed = round(time.perf_counter() - started, 3)
    flagged = {f.change.name for f in result.findings}
    rows, _ = _verify_rows(repo)
    new_broken = [
        r["raw"]
        for r in rows
        if r["status"] == "broken"
        and f"{r['raw']}@{r['file']}:{r['line']}" not in baseline_broken
    ]
    return {
        "detected": bool(symbols & flagged),
        "flagged": sorted(flagged)[:8],
        "verify_detected": any(sym in raw for sym in symbols for raw in new_broken),
        "verify_new_broken": new_broken[:6],
        "suppressed_hint": result.suppressed_hint_count,
        "seconds": elapsed,
    }


def _row(kind: str, name: str, outcome: dict, **extra) -> dict:
    """Assemble one injection result row with noise-word flags."""
    return {
        "kind": kind,
        "name": name,
        **extra,
        **outcome,
        "noise_word": name.lower() in DEFAULT_NOISE_BLOCKLIST,
        "short": len(name) < 4,
    }


def _mutate_python(line: str, cand: dict, kind: str) -> str:
    """Return the definition line changed to simulate a rename or signature change."""
    name = cand["name"]
    if kind == "python-rename":
        return re.sub(rf"\b{re.escape(name)}\b", name + "_renamed", line, count=1)
    if "(" not in line:
        return line
    index = line.index("(") + 1
    inner = line[index:]
    stripped = inner.lstrip()
    if stripped.startswith(("self", "cls")):
        end = (
            index
            + (len(inner) - len(stripped))
            + (4 if stripped.startswith("self") else 3)
        )
        return line[:end] + ", _bench_arg" + line[end:]
    if stripped.startswith(")"):
        return line[:index] + "_bench_arg" + line[index:]
    return line[:index] + "_bench_arg, " + line[index:]


def _inject_phase(repo: Path) -> dict:
    """Inject known drift (renames, signature changes, removed targets) and score detection."""
    rows: list[dict] = []
    readme = _readme_text(repo)
    base_rows, _ = _verify_rows(repo)
    baseline = {
        f"{r['raw']}@{r['file']}:{r['line']}"
        for r in base_rows
        if r["status"] == "broken"
    }
    cands = _python_candidates(repo, readme)
    for kind in ("python-rename", "python-signature"):
        done = 0
        for cand in cands:
            if done >= INJECTIONS_PER_KIND:
                break
            path = repo / cand["file"]
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            before = lines[cand["line"] - 1]
            after = _mutate_python(before, cand, kind)
            if after == before:
                continue
            lines[cand["line"] - 1] = after
            path.write_text("".join(lines), encoding="utf-8")
            try:
                outcome = _detect(repo, {cand["symbol"], cand["name"]}, baseline)
            finally:
                _reset(repo)
            rows.append(
                _row(
                    kind,
                    cand["name"],
                    outcome,
                    symbol=cand["symbol"],
                    node=cand["node"],
                    styles=cand["styles"],
                    file=cand["file"],
                )
            )
            done += 1
    rows.extend(_inject_makefile(repo, readme, baseline))
    rows.extend(_inject_npm(repo, readme, baseline))
    rows.extend(_inject_compose(repo, readme, baseline))
    rows.extend(_inject_script_files(repo, base_rows, baseline))
    return {"injections": rows}


def _inject_makefile(repo: Path, readme: str, baseline: set[str]) -> list[dict]:
    """Rename Makefile targets that the README tells readers to run."""
    makefile = repo / "Makefile"
    if not makefile.exists():
        return []
    text = makefile.read_text(encoding="utf-8", errors="ignore")
    targets = list(dict.fromkeys(re.findall(r"^([A-Za-z][\w.-]*):(?!=)", text, re.M)))
    mentioned = [t for t in targets if re.search(rf"make\s+{re.escape(t)}\b", readme)]
    rows = []
    for target in mentioned[:INJECTIONS_PER_KIND]:
        makefile.write_text(
            re.sub(
                rf"^{re.escape(target)}:",
                f"{target}_renamed:",
                text,
                count=1,
                flags=re.M,
            ),
            encoding="utf-8",
        )
        try:
            outcome = _detect(repo, {target}, baseline)
        finally:
            _reset(repo)
        rows.append(_row("makefile-target-removed", target, outcome))
    return rows


def _inject_npm(repo: Path, readme: str, baseline: set[str]) -> list[dict]:
    """Rename package.json scripts that the README tells readers to run."""
    package = repo / "package.json"
    if not package.exists():
        return []
    text = package.read_text(encoding="utf-8", errors="ignore")
    try:
        scripts = list(json.loads(text).get("scripts", {}))
    except json.JSONDecodeError:
        return []
    mentioned = [
        s
        for s in scripts
        if re.search(rf"(npm run|yarn|pnpm run)\s+{re.escape(s)}\b", readme)
    ]
    rows = []
    for script in mentioned[:INJECTIONS_PER_KIND]:
        package.write_text(
            text.replace(f'"{script}":', f'"{script}_renamed":', 1), encoding="utf-8"
        )
        try:
            outcome = _detect(repo, {script}, baseline)
        finally:
            _reset(repo)
        rows.append(_row("npm-script-removed", script, outcome))
    return rows


def _inject_compose(repo: Path, readme: str, baseline: set[str]) -> list[dict]:
    """Rename compose services that the README tells readers to start."""
    compose = next((repo / n for n in _COMPOSE_NAMES if (repo / n).exists()), None)
    if compose is None:
        return []
    text = compose.read_text(encoding="utf-8", errors="ignore")
    services = list(dict.fromkeys(re.findall(r"^  ([A-Za-z][\w-]*):\s*$", text, re.M)))
    mentioned = [
        s for s in services if re.search(rf"compose\s+\w+.*\b{re.escape(s)}\b", readme)
    ]
    rows = []
    for service in mentioned[:INJECTIONS_PER_KIND]:
        compose.write_text(
            re.sub(
                rf"^  {re.escape(service)}:",
                f"  {service}_renamed:",
                text,
                count=1,
                flags=re.M,
            ),
            encoding="utf-8",
        )
        try:
            outcome = _detect(repo, {service}, baseline)
        finally:
            _reset(repo)
        rows.append(_row("compose-service-removed", service, outcome))
    return rows


def _inject_script_files(
    repo: Path, base_rows: list[dict], baseline: set[str]
) -> list[dict]:
    """Rename script files that README commands verify against."""
    rows = []
    seen: set[str] = set()
    for check in base_rows:
        if check["status"] != "verified" or "exists" not in check["reason"]:
            continue
        match = re.search(r"path '([^']+)' exists", check["reason"])
        if not match:
            continue
        rel = match.group(1)
        # The README means the file next to itself first, then one at the repo root.
        target = (repo / check["file"]).parent / rel
        if not target.is_file():
            target = repo / rel
        if not target.is_file():
            continue
        key = str(target.relative_to(repo))
        if key in seen or len(seen) >= INJECTIONS_PER_KIND:
            continue
        seen.add(key)
        target.rename(target.with_name(target.name + ".renamed"))
        try:
            outcome = _detect(repo, {rel, key}, baseline)
        finally:
            _reset(repo)
        rows.append(_row("script-file-renamed", rel, outcome))
    return rows


def main() -> None:
    """Clone each repository, run all phases, and write one JSON file per repository.

    Returns
    -------
    None
        Results are written under ``--results``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir", type=Path, required=True, help="where to clone repositories"
    )
    parser.add_argument(
        "--results", type=Path, default=Path(__file__).parent / "results"
    )
    parser.add_argument("--only", nargs="*", help="limit to these owner/name slugs")
    parser.add_argument(
        "--phases",
        nargs="*",
        default=["verify", "replay", "inject", "replay_docs", "hook"],
    )
    parser.add_argument(
        "--hook-repo",
        default="",
        help="path of the readme-drift checkout for pre-commit try-repo",
    )
    parser.add_argument(
        "--precommit-path",
        default="",
        help="directory containing the pre_commit package",
    )
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    phases = {
        "verify": _verify_phase,
        "replay": _replay_phase,
        "inject": _inject_phase,
        "replay_docs": _replay_docs_phase,
        "hook": lambda repo: _hook_phase(repo, args.hook_repo, args.precommit_path),
    }
    tool = _tool_info()
    for slug in args.only or REPOS:
        name = slug.replace("/", "__")
        dest = args.workdir / name
        print(f"== {slug}  (tool {tool['branch']}@{tool['commit']})", flush=True)
        record: dict = {"repo": slug, "tool": tool}
        try:
            _clone(slug, dest)
            record["head"] = _git(dest, "rev-parse", "--short", "HEAD")
            record["readmes"] = [str(p.relative_to(dest)) for p in find_readmes(dest)]
            for phase in args.phases:
                started = time.perf_counter()
                try:
                    record[phase] = phases[phase](dest)
                except Exception as exc:  # noqa: BLE001 - one failed phase must not stop the rest
                    record[phase] = {"error": repr(exc)[:300]}
                print(
                    f"   {phase:12} {time.perf_counter() - started:6.1f}s", flush=True
                )
        except Exception as exc:  # noqa: BLE001
            record["error"] = repr(exc)[:300]
            print(f"   FAILED: {exc!r}", flush=True)
        (args.results / f"{name}.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
