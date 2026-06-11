# CI / GitHub Actions

In CI, changes are already committed. Use `--base-ref` to specify what to diff against — typically the PR base branch.

## Basic setup

```yaml
- name: Check README staleness
  run: readme-drift --base-ref origin/${{ github.base_ref }}
```

Do **not** pass `--staged` in CI — there is no staging area in a CI environment.

## Full workflow example

```yaml
name: CI

on:
  pull_request:
    branches: [master]

jobs:
  readme-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history required for git diff

      - name: Install readme-drift
        run: pip install readme-drift

      - name: Check README staleness
        run: readme-drift --base-ref origin/${{ github.base_ref }}
```

## Warn-only in CI

To surface findings without failing the build:

```yaml
- name: Check README staleness
  run: readme-drift --base-ref origin/${{ github.base_ref }} --warn-only
```

## Diffing against a fixed ref

```bash
# Always diff against main, regardless of PR base
readme-drift --base-ref origin/main

# Diff against a specific commit SHA
readme-drift --base-ref abc1234
```
