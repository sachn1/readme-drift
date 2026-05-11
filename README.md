# readme-check

> Detect stale README references after code changes — for pre-commit and CI.

When you rename a function, change a method signature, or remove a class,
`readme-check` warns you if those symbols are referenced in your README —
before the commit lands.

**Zero dependencies. Fully open source. Works offline.**

---

## How it works

```
git diff (staged or vs base branch)
        ↓
  AST diff of changed .py files
  (what functions/classes/signatures changed?)
        ↓
  Scan README for those symbol names
        ↓
  If matched → fail with specific message
  If README was also updated → pass
```

---

## Installation

```bash
pip install readme-check
```

---

## Usage

### As a pre-commit hook (recommended)

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/yourusername/readme-check
    rev: v0.1.0
    hooks:
      - id: readme-check
```

Then install the hook:

```bash
pre-commit install
```

Now every `git commit` that changes `.py` files will check if the README
needs updating.

### As a CLI tool

```bash
# Check staged changes (same as pre-commit)
readme-check --staged

# Check against a specific branch (for CI / PRs)
readme-check --base-ref origin/main

# Warn only — don't fail the build
readme-check --base-ref origin/main --warn-only
```

### In CI (GitHub Actions)

Copy `.github/workflows/readme-check.yml` from this repo, or add this step:

```yaml
- name: Check README staleness
  run: readme-check --base-ref origin/${{ github.base_ref }}
```

---

## Example output

```
readme-check: ❌ README.md may be stale:

  • `Client.connect` signature changed: connect(host, port) → connect(url)
    in src/client.py
    referenced in README.md line 42: …call `Client.connect(host, port)` to connect…

  • `Client.disconnect` was removed
    in src/client.py
    referenced in README.md line 67: …use `Client.disconnect()` when done…

  → Please update the README or run with --no-verify to skip.
```

---

## What it catches

| Change | Detected? |
|---|---|
| Function renamed | ✅ |
| Function removed | ✅ |
| Method signature changed | ✅ |
| Class removed | ✅ |
| New function added (not in README) | ℹ️ reported as FYI |
| README updated alongside code | ✅ passes silently |
| No Python files changed | ✅ skipped |

## What it doesn't catch

- Behavioral changes that don't affect the public API surface
  (for that, you need an LLM — but that's a separate tool)
- Symbols not mentioned in the README

---

## License

MIT