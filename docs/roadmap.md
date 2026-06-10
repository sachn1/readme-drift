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

## v1.0.0 — Stable release ← next

The first stable, production-ready release. Marks confidence in the public API surface, the pre-commit hook contract, and PyPI packaging.

**Exit criteria:**
- No open P0/P1 bugs after at least one full release cycle on PyPI
- Pre-commit hook confirmed working across Python, Node, and Go project layouts
- Public API (`SymbolChange`, `diff_apis`, `diff_config`, `run_check`) considered stable for downstream use

---

## v1.1.0 — Broader prose documentation targets

README is the most visible documentation file, but several others frequently reference code symbols and are just as likely to go stale.

**Planned targets:**
- `CONTRIBUTING.md` — contribution guides reference commands, APIs, and module paths
- `SECURITY.md` — security policies reference versions and contact procedures
- `SUPPORT.md` — support docs reference installation steps and CLI flags
- `MIGRATION.md` — migration guides are the most likely to reference renamed or removed APIs directly
- `docs/` folder — any Markdown files under a `docs/` directory
- Configurable target list via `[tool.readme-drift]` in `pyproject.toml`

---

## v1.2.0 — Fine-grained control

**Planned:**
- Symbol allowlist — symbols to always flag regardless of README mention
- Symbol denylist — symbols to never flag (e.g. internal ones that leak into public API by naming convention)
- README path configuration — explicit include list (`readme_paths`) and additional exclude dirs, so pre-commit users can pin exactly which README files are scanned instead of relying on recursive discovery
- `SymbolChange` model cleanup — `old_signature` currently stores the old *name* for renames and the old *signature string* for signature changes; introduce a dedicated `old_name` field for renames to make the model unambiguous
- Full key-path matching in README (e.g. `scripts.build`) — extend scanner to recognise dot-notation config paths in addition to leaf names
- **Noise suppression** — built-in blocklist of short, high-frequency tokens that are valid symbol names but match too many unrelated README lines (e.g. `name`, `version`, `build`, `test`, `run`, `type`, `url`, `host`, `port`, `debug`, `true`, `false`); configurable `min-symbol-length` threshold (default: 4 characters) to skip single-character and very short tokens from plain-text matching; both the blocklist and threshold are overridable in `[tool.readme-drift]`. This is a hard prerequisite for v1.3.0 — the infra file extractors produce exactly these short tokens.
- `--verbose` flag — print every detected symbol change and its README scan outcome (matched / not found); invaluable for diagnosing false positives and understanding why a check passed or failed

---

## v1.3.0 — Build and infrastructure file coverage

Every Python project has files beyond `.py` and generic config that define named things the README references directly — make targets, container services, CLI entry points, environment variables. These files live in the repo, so no external knowledge is needed; the names are extractable by the same `KeyExtractor` protocol already in place.

**Prerequisite:** noise suppression (v1.2.0) must land first. These extractors produce short tokens (`web`, `db`, `lint`, `test`) that are unacceptably noisy without a blocklist and minimum-length threshold.

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
