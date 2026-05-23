# Roadmap

## v0.1.0 — Shipped

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

## v0.2.0 — First public release ← current

Config file coverage and PyPI distribution.

**Config file support:**
- `.yml` / `.yaml` — GitHub Actions workflows, Docker Compose, Hydra, etc.
- `.json` — `package.json` scripts and dependencies, schema files
- `.toml` — `pyproject.toml`, `Cargo.toml`
- Key-path diffing: flatten nested config to dot-notation paths, detect removed and added leaf key names; cross-referenced against the full opposite-side key set so structural parents (`tool`, `jobs`) are not spuriously reported
- Leaf-segment deduplication: a key name that appears in multiple paths (e.g. `runs-on` in every GitHub Actions job) is reported at most once
- `KeyExtractor` protocol: new file types added by implementing one method and registering a suffix — no other module changes required
- Pre-commit hook updated to trigger on `.yml`, `.yaml`, `.json`, and `.toml` changes in addition to `.py`

**PyPI release:**
- `pyyaml` added as a runtime dependency (TOML and JSON use stdlib)
- Automated publish to PyPI on version tag via trusted publishing (OIDC — no API token secret needed)
- Package installable as `pip install readme-check`
- Registerable as a pre-commit hooks repository

**Deferred from v0.2.0 (added to later milestones):**
- Config-key rename detection — the same-value heuristic is too ambiguous when multiple keys share a value (e.g. many jobs with `runs-on: ubuntu-latest`); deferred to backlog pending a cleaner signal
- Full key-path matching in README (e.g. `scripts.build`) — current version matches leaf names only; full-path matching deferred to v1.2.0

---

## v1.0.0 — Stable release

Promoted from v0.2.x after the public release proves stable in the wild. No new features — this milestone represents confidence in the public API surface, the pre-commit hook contract, and the PyPI packaging. Any critical bug fixes discovered post-v0.2.0 ship here.

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
- Configurable target list via `[tool.readme-check]` in `pyproject.toml`

---

## v1.2.0 — Configuration and fine-grained control

**Planned:**
- Configuration file (`[tool.readme-check]` in `pyproject.toml` or a standalone `readme-check.toml`) for project-level settings
- Symbol allowlist — symbols to always flag regardless of README mention
- Symbol denylist — symbols to never flag (e.g. internal ones that leak into public API by naming convention)
- Source path exclusions — skip diffing specific Python files or directories
- README path configuration — explicit include list (`readme_paths`) and additional exclude dirs, so pre-commit users can pin exactly which README files are scanned instead of relying on recursive discovery
- `SymbolChange` model cleanup — `old_signature` currently stores the old *name* for renames and the old *signature string* for signature changes; introduce a dedicated `old_name` field for renames to make the model unambiguous
- Full key-path matching in README (e.g. `scripts.build`) — extend scanner to recognise dot-notation config paths in addition to leaf names

---

## Backlog (unscheduled)

- Config-key rename detection — needs a reliable signal beyond same-value; candidates include structural similarity of sibling keys or explicit rename hints in commit messages
- `--fix` flag to open the README at the stale line in `$EDITOR`
- JSON output mode for integration with other tools
- VS Code extension
- **Bidirectional README consistency check** — currently the tool is code-change-driven: it only runs when tracked files change. Two possible approaches for the inverse direction:
  1. Keep the existing behaviour and add nothing (README changes that introduce wrong names are out of scope)
  2. When the README changes, extract all backtick/word-boundary symbol-like tokens from it and verify each one exists as an exact match (not a substring) in the current public API — flagging references that don't correspond to any known symbol
