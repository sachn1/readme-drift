# CLI reference

```
readme-drift [OPTIONS]
```

All options can also be set in `pyproject.toml` under `[tool.readme-drift]`. CLI flags take precedence over the config file. See [Configuration](../configuration.md) for the full key list.

---

## Git source

### `--base-ref TEXT`
Git ref to diff against. Default: `HEAD`.

In CI, pass the PR base branch: `--base-ref origin/main`.
In pre-commit mode, this is unused — diffs are taken from the staging area instead.

### `--staged`
Check staged changes only (what you've `git add`-ed). Used by the pre-commit hook automatically — do not pass this manually when using the hook.

### `--repo-root PATH`
Path to the repository root. Auto-detected by walking up from `cwd` if not set.

---

## Source filtering

### `--exclude PATTERN`
Glob pattern for source files or directories to skip. Repeatable.

```bash
readme-drift --exclude "generated/" --exclude "vendor/"
```

This filters **source files** (`.py`, config files). To skip directories during README discovery, use `--readme-exclude-dirs`.

### `--include-private`
Track private (underscore-prefixed) Python symbols. Default: off.

---

## README targeting

### `--readme-paths PATH`
Explicit README file to scan. Repeatable. When set, **disables recursive README discovery** entirely.

```bash
readme-drift --readme-paths README.md --readme-paths docs/API.md
```

!!! warning
    Incompatible with `--readme-exclude-dirs`. When `--readme-paths` is set, `--readme-exclude-dirs` is silently ignored.

### `--readme-exclude-dirs DIR`
Extra directory name to skip during automatic README discovery. Repeatable.

```bash
readme-drift --readme-exclude-dirs vendor --readme-exclude-dirs third_party
```

Has no effect when `--readme-paths` is set.

---

## Symbol filtering

### `--symbol-allowlist SYMBOL`
Always flag this symbol when changed, even if it is not mentioned in the README. Repeatable. Use for critical public API symbols that must be kept in sync.

### `--symbol-denylist SYMBOL`
Never flag this symbol, even if it changed and appears in the README. Repeatable. Takes priority over `--symbol-allowlist` — a symbol on both lists is never flagged.

### `--min-symbol-length N`
Minimum symbol length for **plain-text** (word-boundary) matching. Default: `4`.
Shorter symbols are still matched when they appear inside backtick spans.

Only relevant when `--plain-text-search` is enabled (the default).

### `--noise-blocklist WORD`
Replace the built-in noise blocklist with this word. Repeatable. When provided, the entire built-in list is replaced with only the words given.

To disable noise suppression entirely, set `noise-blocklist = []` in `pyproject.toml` — there is no CLI equivalent for an empty list.

The built-in blocklist suppresses plain-text matching for common tokens that produce false positives (e.g. `name`, `type`, `build`, `run`). See [`readme_drift/constants.py`](https://github.com/sachn1/readme-drift/blob/master/readme_drift/constants.py) for the full default list, split by category.

!!! warning
    `--noise-blocklist` replaces the entire built-in list. If you only want to re-enable one word, use `--noise-allowlist` instead.

!!! note
    Has no effect when `--no-plain-text-search` is set.

### `--noise-allowlist WORD`
Remove a specific word from the built-in noise blocklist. Repeatable. The rest of the built-in list stays active.

```bash
# re-enable plain-text matching for "run" while keeping all other suppressions
readme-drift --noise-allowlist run
```

Use this instead of `--noise-blocklist` when you only want to unlock one or two words from the default suppression list without having to spell out all the others.

!!! note
    Ignored when `--noise-blocklist` is set (that flag replaces the built-in list entirely, making allowlist irrelevant).

!!! note
    Has no effect when `--no-plain-text-search` is set.

---

## Output

### `--plain-text-search` / `--no-plain-text-search`
Match symbols as plain text (word-boundary) in addition to backtick spans. Default: enabled.

Disabling this restricts matching to backtick spans only, which reduces false positives at the cost of missing prose references.

When disabled, `--noise-blocklist` and `--min-symbol-length` have no effect.

### `--warn-only`
Print findings but always exit `0`. The build never fails. Useful for introducing readme-drift into an existing project without blocking CI immediately.

### `--verbose`
Print per-symbol scan outcomes after the main report: flagged, skipped, suppressed by noise filter, or denied.

---

## Option interactions

| Combination | Behaviour |
|---|---|
| `--readme-paths` + `--readme-exclude-dirs` | `--readme-exclude-dirs` is ignored; warning printed |
| `--no-plain-text-search` + `--noise-blocklist` | `--noise-blocklist` is ignored; warning printed |
| `--no-plain-text-search` + `--noise-allowlist` | `--noise-allowlist` is ignored; warning printed |
| `--no-plain-text-search` + `--min-symbol-length` | `--min-symbol-length` is ignored (no plain-text matching runs) |
| `--noise-blocklist` + `--noise-allowlist` | `--noise-allowlist` is ignored; warning printed (`--noise-blocklist` already replaces the built-in list) |
| `--symbol-allowlist X` + `--symbol-denylist X` | Denylist wins; symbol is never flagged |
| `--symbol-allowlist X` (not in README) | Symbol is force-flagged even without a README match |
