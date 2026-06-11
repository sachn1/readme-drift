# Roadmap

## v0.1.0 — Shipped

- Python file support (`.py`) via AST diffing
- Detects removed and signature-changed public functions, methods, and classes
- README scanning via backtick and word-boundary regex patterns
- Recursive README discovery — supports monorepos with per-package READMEs
- Pre-commit hook integration
- CI usage via `--base-ref origin/main`
- `--warn-only` mode for non-blocking runs
- GitHub Actions CI — lint (`ruff`) and `pytest` on every PR to `develop` and `master`
- Semantic versioning with Commitizen — `develop` builds carry `-rc.N`, merging to `master` promotes to release
- Branch strategy: `feature/*` → `develop` → `master`

---

## v0.2.0 — Shipped

Config file coverage, user configurability, performance, and PyPI distribution.

**Config file support:**
- `.yml` / `.yaml` — GitHub Actions workflows, Docker Compose, Hydra, etc.
- `.json` — `package.json` scripts and dependencies, schema files
- `.toml` — `pyproject.toml`, `Cargo.toml`
- Key-path diffing: flatten nested config to dot-notation paths, detect removed and added leaf key names; cross-referenced against the full opposite-side key set so structural parents (`tool`, `jobs`) are not spuriously reported
- Leaf-segment deduplication: a key name that appears in multiple paths (e.g. `runs-on` in every GitHub Actions job) is reported at most once
- `KeyExtractor` protocol: new file types added by implementing one method and registering a suffix — no other module changes required
- Pre-commit hook updated to trigger on `.yml`, `.yaml`, `.json`, and `.toml` changes in addition to `.py`

**User configurability:**
- `--include-private` flag — opt in to tracking private (underscore-prefixed) functions and methods
- `--exclude` option — skip specific Python files or directories from diffing
- Plain-text occurrence matching — configurable flag (default on) to flag symbol names found outside backtick spans
- `[tool.readme-drift]` in `pyproject.toml` — project-level defaults for all CLI flags; `--repo-root` pre-parsed so config is located before argument defaults are applied
- All boolean flags use `--flag=true/false` syntax via a shared `_parse_bool` helper — consistent across all options

**Performance:**
- Lazy content reads — file contents read only for files whose changed symbols actually appear in a README

**Observability:**
- `Makefile` — `make check` mirrors CI exactly (ruff + pytest with coverage gate)

**PyPI release:**
- `pyyaml` added as a runtime dependency (TOML and JSON use stdlib)
- Automated publish to PyPI on version tag via trusted publishing (OIDC — no API token secret needed)
- Package installable as `pip install readme-drift`
- Registerable as a pre-commit hooks repository

**Deferred to backlog:**
- Python function rename detection — the "same params = rename" heuristic was too unreliable; deferred pending a reliable signal
- Config-key rename detection — the same-value heuristic is too ambiguous; deferred to backlog
- Full key-path matching in README (e.g. `scripts.build`) — current version matches leaf names only

---

## v1.0.0 — Shipped

The first stable, production-ready release. Public API (`SymbolChange`, `diff_apis`, `diff_config`, `run_check`) considered stable for downstream use.

---

## v1.0.1 — Shipped

Click migration, `--staged` bug fix, and trunk-based branching.

**CLI:**
- Migrated from argparse to `click` — boolean flags are now bare flags (`--staged`, `--warn-only`, `--include-private`) and toggle pairs (`--plain-text-search` / `--no-plain-text-search`)
- Fixed `--staged` pre-commit hook error (`expected one argument`) — `is_flag=True` means bare `--staged` = True; hook entry simplified to `readme-drift --staged`

**Code quality:**
- `readme_drift/constants.py` — extracted `DEFAULT_NOISE_BLOCKLIST`, `README_NAMES`, `README_EXTENSIONS`, `README_SKIP_DIRS` out of private definitions scattered across modules

**Workflow:**
- Simplified to trunk-based: `feature/*` or `bugfix/*` → PR → `master` directly; no `develop` branch, no RC cycle

---

## v1.1.0 — Fine-grained control ← next release

Symbol filtering, noise suppression, README targeting, and verbose output. All items below are implemented on the current branch.

**Symbol filtering:**
- `--symbol-allowlist` — always flag symbol when changed, even without a README match; for critical public API
- `--symbol-denylist` — never flag symbol, even if changed and found in README; takes priority over allowlist
- `--min-symbol-length` — plain-text matching only applies to symbols ≥ N characters (default: 4); shorter symbols still matched inside backticks
- `--noise-blocklist` — replace the built-in suppression list; disable entirely via `noise-blocklist = []` in `pyproject.toml`; prerequisite for v1.3.0

**README targeting:**
- `--readme-paths` — explicit README list, disables recursive discovery entirely
- `--readme-exclude-dirs` — add extra dirs to skip during discovery without changing the built-in skip list

**Output:**
- `--verbose` — per-symbol trace: shows whether each changed symbol was flagged, suppressed, or skipped and why

**Model:**
- `SymbolChange.old_name` — dedicated field for the pre-rename name, separate from `old_signature`; `key_paths` stores full dot-notation paths (e.g. `["scripts.build"]`) so the README is searched for both leaf names and full paths

**Documentation:**
- MkDocs Material docs site at https://sachn1.github.io/readme-drift — auto-deployed on every master push via `docs.yml`

---

## v1.2.0 — Broader prose documentation targets

README is the most visible documentation file, but several others frequently reference code symbols and are just as likely to go stale.

**Planned targets:**
- `CONTRIBUTING.md` — contribution guides reference commands, APIs, and module paths
- `SECURITY.md` — security policies reference versions and contact procedures
- `SUPPORT.md` — support docs reference installation steps and CLI flags
- `MIGRATION.md` — migration guides are the most likely to reference renamed or removed APIs directly
- `docs/` folder — any Markdown files under a `docs/` directory
- Configurable target list via `[tool.readme-drift]` in `pyproject.toml`

---

## v1.3.0 — Build and infrastructure file coverage

Every Python project has files beyond `.py` and generic config that define named things the README references directly — make targets, container services, CLI entry points, environment variables. These files live in the repo, so no external knowledge is needed; the names are extractable by the same `KeyExtractor` protocol already in place.

**Prerequisite:** noise suppression (v1.1.0) must land first. These extractors produce short tokens (`web`, `db`, `lint`, `test`) that are unacceptably noisy without a blocklist and minimum-length threshold.

**Infrastructure changes required:**
- Filename-keyed extractor registry alongside the existing suffix-keyed `_EXTRACTORS` — needed for `Makefile` (no suffix) and compose files (`.yml` suffix already claimed by the generic `YamlExtractor`)
- Pre-commit hook `types_or` / `files` pattern updated to trigger on the new filenames

**Planned file types:**

- **`Makefile` / `GNUmakefile` / `makefile`** (filename-triggered, no suffix) — extract target names from non-indented `target:` lines and `.PHONY` declarations; catches `make lint` becoming `make check` or a `make docs` target being removed from a README's development guide
- **`docker-compose.yml` / `docker-compose.yaml` / `compose.yml` / `compose.yaml`** (filename-triggered) — extract top-level service names from `services:` only, not the full YAML tree; catches `docker compose up web` references when a service is renamed or removed. Filename-triggered to avoid applying the deep-flatten `YamlExtractor` to compose files.
- **`pyproject.toml`** (specialized extraction, beyond current generic TOML flattening) — extract CLI entry point names from `[project.scripts]` and `[tool.poetry.scripts]` (these are the commands users actually type after install, e.g. `readme-drift`); extract optional dependency group names from `[project.optional-dependencies]` and `[tool.poetry.group.*]` (catches `pip install pkg[dev]` or `pip install pkg[all]` references going stale)
- **`tox.ini`** — extract `[testenv:name]` section names (e.g. `lint`, `py311`, `coverage`) via stdlib `configparser`; catches `tox -e lint` references when an environment is renamed or removed
- **`Dockerfile`** — extract multi-stage build target names from `FROM ... AS name` lines; catches `docker build --target builder` references when a stage is renamed or removed
- **`.env.example` / `.env.template` / `.env.sample`** — extract variable names from `KEY=value` lines; catches renamed environment variables in setup and deployment guides. Gated behind noise suppression — variable names like `HOST`, `PORT`, `DEBUG` are high-collision.

**Deferred from this version:**
- `setup.cfg` — largely superseded by `pyproject.toml`; diminishing returns
- `Taskfile.yml` / `Taskfile.yaml` (go-task) — same suffix collision as compose files; deferred until filename-keyed registry is proven stable
- `Cargo.toml` feature / binary / workspace member names — Rust ecosystem, separate scope
- `requirements.txt` package names — package names frequently overlap with common English words; noise suppression alone is insufficient
- Kubernetes manifest `metadata.name` values — insufficient signal without knowing which resource kinds the README references; k8s YAML is structurally identical to other YAML
- Shell script internals (function names, flag parsing) — requires Bash/POSIX parsing; a different class of problem

---

## Backlog (unscheduled)

- **Python rename detection** — removed in v0.2.x; the "same params = rename" heuristic produced false positives for zero-parameter functions and any unrelated functions that happened to share parameter names. Needs a reliable signal (e.g. git-level rename tracking, or AST body similarity) before it can be reintroduced. Config-key rename detection has the same problem with shared values (e.g. `runs-on: ubuntu-latest` across many jobs).
- `--fix` flag to open the README at the stale line in `$EDITOR`
- JSON output mode for integration with other tools
- VS Code extension
- **Bidirectional README consistency check** — currently the tool is code-change-driven: it only runs when tracked files change. Two possible approaches for the inverse direction:
  1. Keep the existing behaviour and add nothing (README changes that introduce wrong names are out of scope)
  2. When the README changes, extract all backtick/word-boundary symbol-like tokens from it and verify each one exists as an exact match (not a substring) in the current public API — flagging references that don't correspond to any known symbol
