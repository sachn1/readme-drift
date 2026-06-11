# Configuration

All CLI options can be set permanently in `pyproject.toml` under `[tool.readme-drift]`. CLI flags always take precedence over the file.

`pyproject.toml` is discovered by walking up from the current directory, or from `--repo-root` if set. If no `[tool.readme-drift]` section is present, all defaults apply.

## Full example

```toml
[tool.readme-drift]
# Git ref to diff against. Default: "HEAD"
base-ref = "origin/main"

# Print findings but never fail the build. Default: false
warn-only = false

# Track private (underscore-prefixed) symbols. Default: false
include-private = false

# Glob patterns for source files/dirs to skip. Default: []
exclude = ["generated/", "vendor/"]

# Match symbols as plain text in addition to backtick spans. Default: true
plain-text-search = true

# Minimum symbol length for plain-text matching. Default: 4
min-symbol-length = 4

# Replace built-in noise blocklist. Default: built-in list (see constants.py)
# Set to [] to disable noise suppression entirely.
noise-blocklist = ["run", "build"]

# Symbols to always flag when changed, even if not in README. Default: []
symbol-allowlist = ["MyPublicClass", "critical_function"]

# Symbols to never flag. Default: []
symbol-denylist = ["_internal_helper"]

# Explicit README paths to scan (disables discovery). Default: [] (auto-discover)
readme-paths = ["README.md", "docs/API.md"]

# Extra dirs to skip during README discovery. Default: []
# Ignored when readme-paths is set.
readme-exclude-dirs = ["vendor", "third_party"]
```

## Key reference

| Key | Type | CLI equivalent | Default |
|---|---|---|---|
| `base-ref` | string | `--base-ref` | `"HEAD"` |
| `staged` | bool | `--staged` | `false` |
| `warn-only` | bool | `--warn-only` | `false` |
| `include-private` | bool | `--include-private` | `false` |
| `plain-text-search` | bool | `--plain-text-search` / `--no-plain-text-search` | `true` |
| `min-symbol-length` | int | `--min-symbol-length` | `4` |
| `exclude` | list of strings | `--exclude` (repeatable) | `[]` |
| `noise-blocklist` | list of strings | `--noise-blocklist` (repeatable) | built-in default |
| `symbol-allowlist` | list of strings | `--symbol-allowlist` (repeatable) | `[]` |
| `symbol-denylist` | list of strings | `--symbol-denylist` (repeatable) | `[]` |
| `readme-paths` | list of strings | `--readme-paths` (repeatable) | `[]` (auto-discover) |
| `readme-exclude-dirs` | list of strings | `--readme-exclude-dirs` (repeatable) | `[]` |

## Noise blocklist default

The built-in noise blocklist suppresses plain-text matching for tokens too common to be meaningful README references. The full list is in [`readme_drift/constants.py`](https://github.com/sachn1/readme-drift/blob/master/readme_drift/constants.py), split into three categories:

- **Literals** — `true`, `false`, `none`, `null`, `yes`, `no`, `on`, `off`
- **Infrastructure keys** — `name`, `version`, `type`, `url`, `host`, `port`, `path`, `file`, `dir`, `key`, `value`, `data`, `list`, `mode`, `id`, `tag`, `ref`, `src`, `api`
- **Build commands** — `run`, `build`, `test`, `lint`, `debug`, `env`, `log`, `use`

Tokens on this list are still matched when they appear inside backtick spans.
