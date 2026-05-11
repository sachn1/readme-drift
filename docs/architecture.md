# Architecture

`readme-check` detects stale README references after code changes. When a public symbol — a function, method, or class — is renamed, removed, or has its signature changed, the tool warns if that symbol is still mentioned in a README, before the commit lands.

---

## Pipeline

```
git diff (staged or vs base branch)
        │
        ▼
  Changed .py files + old/new source
  (via git show)
        │
        ▼
  AST diff per file
  (what functions/classes/signatures changed?)
        │
        ▼
  Scan all README files for those symbol names
  (backtick references + word-boundary plain text)
        │
        ▼
  If matched → fail (README may be stale)
  If no matches → pass
  If no Python files changed → skip
```

---

## Module Overview

```
readme_check/
├── models.py       # All shared data classes (GitDiffResult, SymbolChange,
│                   # ReadmeMatch, StalenessFinding, CheckResult, …)
├── git.py          # Git integration — diffs, file content retrieval,
│                   # README discovery (recursive, case-insensitive)
├── ast_diff.py     # AST parsing and symbol diffing — extracts the public
│                   # API surface and computes what changed between versions
├── scanner.py      # README scanning — searches for symbol names using
│                   # regex (backtick and word-boundary patterns)
├── checker.py      # Orchestrator — wires git → AST diff → scanner → result
├── report.py       # Formats a CheckResult into human-readable terminal output
└── cli.py          # Entry point — parses CLI args, calls checker, exits 0/1
```

### Data flow between modules

```
cli.py
  └─► checker.py
        ├─► git.py          → GitDiffResult
        ├─► ast_diff.py     → list[SymbolChange]
        ├─► scanner.py      → dict[symbol, list[ReadmeMatch]]
        └─► report.py       → str (terminal output)
```

All types that cross module boundaries live in `models.py` to avoid circular imports.

---

## Key design decisions

**AST-based diffing, not line diffs.** A line diff would produce false positives (e.g. reformatting) and miss renames. Parsing both file versions into ASTs and comparing the public API surface gives signal only when the interface actually changes.

**Public symbols only.** Names starting with `_` are ignored. Internal implementation changes are not the README's concern.

**Rename detection.** A function removed and a function added with identical parameter lists is treated as a rename, not a deletion + addition. This avoids a false positive when someone runs a rename refactor.

**Recursive README discovery.** All README files in the repository are found and scanned (excluding `.git`). This supports monorepos where each package has its own README.

**A README update does not bypass the check.** Touching the README in the same diff does not auto-pass. The full scan still runs, and the result is based on whether any changed symbols remain referenced. A correctly updated README naturally produces zero findings and passes; a partially updated one correctly fails.
