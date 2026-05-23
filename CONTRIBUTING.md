# Contributing

Thanks for your interest in contributing to readme-drift.

---

## Before you start

For anything beyond a small bug fix, **open an issue first** to discuss the change. This avoids situations where a PR arrives that duplicates in-progress work or heads in a direction the project won't take.

---

## Development setup

```bash
git clone https://github.com/sachn1/readme-drift
cd readme-drift
poetry install
```

Run the test suite:

```bash
poetry run pytest
```

Run the linter:

```bash
poetry run ruff check .
poetry run ruff format --check .
```

---

## Branch strategy

```
feature/*  →  develop  →  master
```

- **All PRs target `develop`**, never `master` directly.
- `master` is the release branch — only merged from `develop` when cutting a release.
- Name your branch `feature/<short-description>` for new work or `bugfix/<short-description>` for fixes.

---

## Commit conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Commitizen enforces this and drives the version bump automatically:

| Commit type | Version bump |
|---|---|
| `fix: ...` | Patch (`0.0.x`) |
| `feat: ...` | Minor (`0.x.0`) |
| `feat!: ...` or `BREAKING CHANGE:` in footer | Major (`x.0.0`) |
| `docs:`, `chore:`, `test:`, `refactor:` | No bump |

Examples:

```
feat: add XML config file support via XmlExtractor
fix: report leaf name instead of array index for list keys
feat!: rename --warn-only flag to --no-fail

BREAKING CHANGE: --warn-only is now --no-fail; update any CI scripts
```

---

## Tests

- All existing tests must pass: `poetry run pytest`
- New behaviour must be covered by tests — bug fixes included (add a regression test that would have caught the bug).
- Tests live in `tests/` and mirror the module they cover (e.g. `tests/test_config_diff.py` for `readme_drift/config_diff.py`).

---

## Extending the tool

### Adding support for a new config file type

Implement the `KeyExtractor` protocol and register the suffix — no other module needs to change:

```python
# readme_drift/config_diff.py

class XmlExtractor:
    def extract(self, content: str) -> dict[str, str]:
        # return {dot-notation-key-path: string-value} for all leaf nodes
        ...

_EXTRACTORS[".xml"] = XmlExtractor()
```

The protocol is `@runtime_checkable`, so `isinstance(XmlExtractor(), KeyExtractor)` works in tests.

---

## Pull request checklist

- [ ] Targets `develop`, not `master`
- [ ] Follows conventional commit format
- [ ] All tests pass (`poetry run pytest`)
- [ ] Linter clean (`poetry run ruff check .`)
- [ ] New behaviour has tests
