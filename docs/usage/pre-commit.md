# Pre-commit hook

## Setup

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/sachn1/readme-drift
    rev: v1.0.1  # use the latest release tag
    hooks:
      - id: readme-drift
```

Install the hook:

```bash
pre-commit install
```

No extra `args` needed. The hook is pre-configured to check **staged changes** — everything you've `git add`-ed. Do not pass `--staged` yourself; it is already set in the hook entry.

## How it triggers

The hook fires on `git commit` when any of these file types are staged:

`.py` · `.yml` · `.yaml` · `.json` · `.toml`

If none of those file types changed, the hook skips silently.

## Warn-only mode

To print findings without blocking commits:

```yaml
hooks:
  - id: readme-drift
    args: ["--warn-only"]
```

## Excluding files

```yaml
hooks:
  - id: readme-drift
    args: ["--exclude", "generated/", "--exclude", "vendor/"]
```

## Common issues

**`--staged` argument error** — Do not add `--staged` or `--staged true` to `args`. The hook entry already sets it. Duplicating the flag causes an argument parse error.

**Hook not triggering** — Verify `pre-commit install` has been run and the staged files match the `types_or` list above.
