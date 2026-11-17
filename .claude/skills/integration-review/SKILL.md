---
name: integration-review
description: Deep cross-file consistency review for readme-drift — checks that docs, CI workflows, pre-commit hook config, the composite Action, and pyproject.toml all agree with each other and with the actual code. Manual trigger only, read-only (report findings, don't auto-fix). Use when asked to audit the repo, check "everything is covered", or before cutting a release.
---

# Integration review

This project's own bugs don't show up in `ruff check` or `pytest` — they show up as one file saying something another file contradicts: a doc describing a flag that no longer exists, a version pin nobody updates, a pre-commit trigger list missing a file type the code now handles. `readme-drift` catches this pattern for README.md against code; nothing catches it for the rest of the repo. This skill is that manual, on-demand pass.

Read-only: report findings, ranked by priority. Do not edit files unless the user explicitly asks you to apply a fix afterward.

## What to check

### 1. Run the real gates, not just a mental check

```bash
poetry install
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest --cov=readme_drift --cov-report=term-missing --cov-fail-under=80
```

`ruff check` passing does **not** mean `ruff format --check` passes — they're different commands and this repo's `make lint` runs both. Run the literal `make check` sequence, don't infer it from reading the Makefile.

### 2. CLI surface vs. documentation

```bash
poetry run python -m readme_drift.cli --help
```

Diff this against `docs/usage/cli-reference.md` — every flag in `--help` must have a `### --flag` section there, and vice versa (a documented flag that no longer exists in `--help` is just as much a bug).

### 3. Version pins

Find every hardcoded `vX.Y.Z`-shaped string across `*.md` and workflow files:

```bash
grep -rn "rev: v[0-9]\|@v[0-9]\+\.[0-9]\+\.[0-9]\+" --include="*.md" --include="*.yml" --include="*.yaml" .
```

For each hit, confirm it matches the current version in `pyproject.toml`'s `[tool.poetry]` section, **and** that its file is listed in `[tool.commitizen].version_files` so it stays correct on the next bump. A hit that's both stale *and* missing from `version_files` is a compounding bug — it'll never self-correct. Historical version headers (e.g. changelog/roadmap entries describing what shipped in a past release) are not stale — don't flag those.

### 4. Pre-commit / CI / Action wiring

- `.pre-commit-hooks.yaml`'s `types_or` list must cover every file type `readme_drift/git.py` actually classifies as a source or config file (cross-check `CONFIG_SUFFIXES`, `CONFIG_FILENAMES` in `config_diff.py`, plus `.py`). A file type the code handles but pre-commit never triggers on is a silent gap — the hook simply won't run.
- `action.yml`: confirm every `${{ ... }}` expression is passed through `env:` before being used in a `run:` script body, never spliced directly into the script text. Direct interpolation is a script-injection vector if a consuming workflow ever wires attacker-influenced data into an input.
- Confirm `action.yml`'s inputs are actually documented somewhere a user would find them (README and/or `docs/usage/ci.md`).

### 5. Docs that mirror each other

`docs/index.md` is largely a duplicate of README.md's content for the MkDocs site; `docs/usage/pre-commit.md` and `docs/usage/ci.md` duplicate parts of README's Usage section. These do not update together automatically — check each one individually for the same facts (supported file types, current CLI flags, current version pins, current onboarding guidance) rather than assuming README being correct means the docs site is too.

### 6. Prose claims vs. actual repo state

`CONTRIBUTING.md`'s branch-strategy description, in particular, is prone to drifting behind reality. Verify prose claims about branching/workflow against what's actually true:

```bash
git branch -a
cat .github/workflows/*.yml
```

### 7. Dependency hygiene

For each `[tool.poetry.group.dev.dependencies]` entry, confirm it's actually used somewhere (Makefile, CI, a config section). A dependency like a type-stub package with no corresponding tool invocation anywhere is dead weight — flag it, don't remove it silently.

### 8. Docstring convention

The project uses numpy-format docstrings (see `CONTRIBUTING.md`, "Docstrings"):

- Module, class (public or private), private function/method, test function/fixture/helper, and property: **one line**.
- Public function or method in `readme_drift/`: **full numpy docstring**, with a `Parameters` section when it takes arguments, a `Returns` section when it returns a value, and `Raises` when it raises deliberately.

`ruff` (`extend-select = ["D"]`, `convention = "numpy"`) checks section formatting and `tests/test_docstrings.py` checks the structure above, so a clean gate run in step 1 already covers most of this. Still verify by hand what neither can see:

- Parameter names and types in a docstring match the actual signature (a stale `Parameters` entry after a rename is the same drift this tool exists to catch).
- `Returns` / `Raises` describe what the code really does now.
- A new public function added since the last review has a real numpy docstring, not a placeholder.
- The CLI `main` docstring keeps its `\f` marker; without it, the whole numpy block leaks into `--help` output.

```bash
poetry run ruff check . --select D
poetry run pytest tests/test_docstrings.py -q
```

### 9. Multi-document consistency (README, docs site, CLI, Action)

The same facts live in several files. Each fact has **one authoritative source**; every other place is a copy that must be checked against it.

| Fact | Authoritative source | Copies to check |
|---|---|---|
| CLI flags | click options in `readme_drift/cli.py` | `docs/usage/cli-reference.md`, README config table, `docs/configuration.md` |
| Config keys | click options + `tips` | README config table, `docs/configuration.md` key reference and example |
| Current version | `pyproject.toml` | every `rev:` / `@v` pin (must be in `version_files`) |
| Action inputs | `action.yml` | `docs/usage/ci.md`, README CI section |
| Supported file types | `git.py`, `config_diff.py`, `.pre-commit-hooks.yaml` | README "What it catches", `docs/index.md`, `docs/usage/pre-commit.md` |
| Onboarding guidance (warn-only, backticks) | README | `docs/index.md`, `docs/usage/pre-commit.md`, `docs/usage/ci.md` |
| Shipped vs planned releases | `git tag` and GitHub releases | `docs/roadmap.md` headings |

**Automated first.** `tests/test_docs_sync.py` already covers CLI flags, config keys, version pins and Action inputs. A failure there is a High finding. When a new fact gets mirrored in more than one file, add it to the table above **and** extend that test.

**Then by hand**, for what a test cannot judge:

- **Redundancy** — a paragraph repeated in three or more places. Intentional mirrors (README and `docs/index.md`) are fine; a third copy should become a link.
- **Stale prose** — compare `git tag --sort=-v:refname | head` with `docs/roadmap.md`: anything marked "Planned" that has shipped, or "Shipped" that has not.
- **Orphans** — `docs/*.md` files missing from `nav:` in `mkdocs.yml` (they build but nobody finds them), and relative links that point nowhere.
- **Guidance gaps** — a recommendation present in README but absent from the docs page a user of that integration (hook, CI, CLI) would actually read.
- **Dogfood** — run `poetry run readme-drift --base-ref origin/master` on the branch and confirm the tool does not flag its own README.

## Reporting

Output a punch list ranked most-severe first:

- **Critical** — security issues, or something that would break CI/publish/install for every user
- **High** — a real functional gap a user would hit (e.g., a hook that silently never triggers)
- **Medium** — stale or inconsistent documentation that could mislead but doesn't break anything (including docstrings that no longer match their signature)
- **Low** — cosmetic or dependency-hygiene nits

For each finding: file path, what's wrong, and a one-line suggested fix. If nothing is wrong in a category, say so briefly rather than omitting it — an empty section is a claim that you checked, not that you skipped it.
