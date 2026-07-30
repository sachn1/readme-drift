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
feature/*  or  bugfix/*  →  PR  →  master
```

Trunk-based: there is no `develop` branch and no RC cycle. All PRs target `master` directly.

- Name your branch `feature/<short-description>` for new work or `bugfix/<short-description>` for fixes.
- `master` is the release branch — merging to it triggers an automatic version bump and, on the resulting tag, a PyPI publish.

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

### Adding support for a new config-like file type

Implement the `KeyExtractor` protocol — no other module needs to change. Two registration paths depending on how the file is identified:

**By suffix** (e.g. a new structured format):

```python
# readme_drift/config_diff.py

class XmlExtractor:
    def extract(self, content: str) -> dict[str, str]:
        # return {dot-notation-key-path: string-value} for all leaf nodes
        ...

_EXTRACTORS[".xml"] = XmlExtractor()
```

**By exact filename** (for files with no distinguishing suffix, or where the suffix is already claimed by a generic extractor — e.g. `Makefile`, or `docker-compose.yml` needing different handling than plain YAML):

```python
_FILENAME_EXTRACTORS["Taskfile.yml"] = TaskfileExtractor()
```

`_FILENAME_EXTRACTORS` is checked before the suffix-keyed `_EXTRACTORS`, so a filename match always wins. `CONFIG_SUFFIXES` and `CONFIG_FILENAMES` (used by `git.py` to decide which changed files to diff) are both derived automatically from these two dicts — adding an entry is the only change required.

The protocol is `@runtime_checkable`, so `isinstance(XmlExtractor(), KeyExtractor)` works in tests. See `MakefileExtractor` in `readme_drift/config_diff.py` for a real filename-keyed example.

### Adding support for a new language's public-API diffing

This is a different, larger change than adding a config extractor — `ast_diff.py` is hardwired to Python's stdlib `ast` module, not behind a pluggable protocol. It's wired into `drift_checker.run_check()`'s own loop and `git.py`'s `changed_py_files` bucket directly. Supporting another language means a new parser dependency (Python's `ast` can't parse other languages), a new diff module, and edits to `run_check()`, `git.py`, and `models.GitDiffResult` — open an issue to discuss scope before starting this kind of change.

---

## Before cutting a release

`readme-drift` catches drift in README.md against code, but nothing catches drift between the *rest* of the repo's own docs, CI config, and pre-commit wiring — that class of bug (a stale version pin, a doc describing a removed flag, a pre-commit trigger list missing a file type the code now handles) has to be checked by hand. If you're working in Claude Code, run `/integration-review` before a release or after a batch of changes that touch CI/docs/config together — it's a manual, read-only pass, not something that runs automatically.

---

## Pull request checklist

- [ ] Targets `master` (trunk-based — no `develop` branch)
- [ ] Follows conventional commit format
- [ ] All tests pass (`poetry run pytest`)
- [ ] Linter clean (`poetry run ruff check .`)
- [ ] New behaviour has tests
- [ ] Optional: if the change touches CI, docs, `pyproject.toml`, or the pre-commit/Action config, run `/integration-review` (Claude Code) before committing to catch cross-file drift a linter won't
