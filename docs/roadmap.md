# Roadmap

## v0.1.0 — Current

- Python file support (`.py`) via AST diffing
- Detects renamed, removed, and signature-changed public functions, methods, and classes
- README scanning via backtick and word-boundary regex patterns
- Recursive README discovery — supports monorepos with per-package READMEs
- Pre-commit hook integration
- CI usage via `--base-ref origin/main`
- `--warn-only` mode for non-blocking runs
- GitHub Actions CI — lint (`ruff`) and `pytest` on every PR to `develop` and `master`
- Semantic versioning with Commitizen — `develop` builds carry `-rc.N`, merging to `master` promotes to release
- Branch strategy: `feature/*` → `develop` → `master`

---

## v0.2.0 — Config file support + PyPI release

Production code does not live alone. Configuration files — CI pipelines, deployment manifests, package definitions — are also documented in READMEs, and they change too. This version extends coverage to those files and ships the package publicly.

**Config file support:**
- `.yml` / `.yaml` — GitHub Actions workflows, Docker Compose, Ansible, etc.
- `.json` — `package.json` scripts and dependencies, schema files
- `.toml` — `pyproject.toml`, `Cargo.toml`
- Key-path diffing: detect renamed keys, removed sections, and structural changes (analogous to what AST diffing does for Python)
- A shared extractor interface so new file types can be added by implementing one method, without touching the scanner or reporter

**PyPI release:**
- Publish `readme-check` to PyPI
- Automated release on tag via CI
- Register as a pre-commit hooks repository

---

## v0.3.0 — Broader prose documentation targets

README is the most visible documentation file, but several others frequently reference code symbols and are just as likely to go stale.

**Planned targets:**
- `CONTRIBUTING.md` — contribution guides reference commands, APIs, and module paths
- `SECURITY.md` — security policies reference versions and contact procedures
- `SUPPORT.md` — support docs reference installation steps and CLI flags
- `MIGRATION.md` — migration guides are the most likely to reference renamed or removed APIs directly
- `docs/` folder — any Markdown files under a `docs/` directory
- Configurable target list via `[tool.readme-check]` in `pyproject.toml`

---

## v0.4.0 — Configuration and fine-grained control

**Planned:**
- Configuration file (`[tool.readme-check]` in `pyproject.toml` or a standalone `readme-check.toml`) for project-level settings
- Symbol allowlist — symbols to always flag regardless of README mention
- Symbol denylist — symbols to never flag (e.g. internal ones that leak into public API by naming convention)
- Path exclusions — skip checking specific files or directories

---

## Backlog (unscheduled)

- `--fix` flag to open the README at the stale line in `$EDITOR`
- JSON output mode for integration with other tools
- VS Code extension
