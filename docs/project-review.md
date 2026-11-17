# Project review and closure plan

Status snapshot: v3.2.0 (latest tag on `origin/master`). This document records what is good, what should change, and where the scope ends, so the project can be brought to a defined finish.

> Verified against the local checkout (v3.0.1 plus a fetch of the remote). Items marked **(verify)** were inferred from commit messages or the roadmap and should be checked against v3.2.0 code before acting.

---

## 1. Definition of terms

**Claim** — a statement in the documentation that can be true or false about the repository. Today the tool treats a README as a bag of words and asks: "does this changed name appear anywhere?". The proposed model treats the README as a list of claims, each with a kind and a verifier:

| Kind | Example in README | True when |
|---|---|---|
| name | `` `Client.connect` `` | the symbol exists in the public API |
| command | `make lint`, `docker compose up web`, `npm run build` | the repo-owned arguments resolve (target, service, script) |
| flag | `myapp --verbose` | the flag is defined by the project's own CLI |
| path | `docs/usage/ci.md`, `-f k8s/x.yaml` | the file exists |
| env var | `export DATABASE_URL=...` | the variable is read in code or listed in `.env.example` |
| code example | a Python block calling `connect(url=...)` | imports resolve and arguments match the signature |
| link | `[Config](configuration.md#keys)` | file and anchor exist |
| version | "Python 3.9+", `rev: v3.0.0` | matches `requires-python` / the latest tag |

Each claim ends in one of three states: **verified**, **broken**, or **unverifiable**. Only *broken* fails a run.

**Owned names** — names defined by files in this repo. The tool verifies these. It does not verify the syntax of third-party tools (`docker run -it` is Docker's concern; the `web` in `docker compose up web` is ours).

---

## 2. Local model question

- **Laya** (https://laya-ai.com/laya-vs-jev) — an open-weight *decision* model for typed decisions (pick a label, score, yes/no), not text generation. The vendor page states Apache 2.0, self-hosted (CPU is enough at low volume; `laya-serve`, ollaya on port 11435), and an endpoint compatible with the hosted Jev API (`POST /v1/systemone`). Parameter count and file size are not stated on that page. Its own zero-shot numbers show it is close to the hosted Jev model on 2-label tasks (SST-2 0.920 vs 0.963) but weak on many labels (Banking77 0.363 vs 0.813) and over-confident there; the page advises keeping choices under ~20. These are vendor benchmarks and are not validated for documentation drift. (An earlier search wrongly matched an unrelated EEG model, arXiv 2603.16281.)
- **Where Laya fits:** as the *judge* over a small label set, e.g. `{stale, still-correct, unrelated}` for a (README claim, code change) pair. It does not generate text, so it cannot extract claims from prose; that would need a generative model (e.g. Qwen) or stays out of scope.
- **Gate before adopting:** build a labelled set of ~100 (claim, change) pairs from this repo's real history, run Laya zero-shot, and measure precision. Ship as advisory only if precision is high enough that warnings are trusted; otherwise stay deterministic. Verify the license and weights on the model card, not the comparison page.
- **Embeddings (SQLite cache)** — useful only for *retrieval* ("which paragraph relates to this diff"). They cannot judge truth. For identifiers, exact match already beats them.
- **Small generative model (e.g. Qwen 0.5B–3B)** — Qwen2.5 small GGUF builds are listed under Apache 2.0; confirm on the official model card before shipping, and re-check for newer releases. Suitable only as an **opt-in advisory layer**, never a gate.
- **Recommendation:** claims verification is deterministic and should ship first. A model, if added, has one narrow job: extract claims from *prose* ("listens on port 8080"). Verification stays deterministic. Prefer a bring-your-own endpoint (Ollama or any OpenAI-compatible URL) over bundling weights; download nothing without an explicit `readme-drift model pull`.

---

## 3. Keep — good choices

- **AST-based diffing** instead of line diffs: signal only on real interface changes.
- **`KeyExtractor` protocol + filename-keyed registry**: new file types without touching other modules. This becomes the *fact index* for claim verification.
- **Filter priority** (denylist > allowlist > noise suppression) with a documented order.
- **Noise controls**: `min-symbol-length`, blocklist, allowlist, `--verbose` trace.
- **Distribution**: pre-commit hook, GitHub Action, `pip install`, `--init` scaffold, trusted PyPI publishing.
- **Config via `[tool.readme-drift]`**, CLI overrides file.
- **Small dependency footprint** (`click`, `pyyaml`); offline and fast.
- **Trunk-based flow + commitizen** release automation.
- **Test discipline**: 133 tests at v3.0.1, strong coverage in core diff/scan modules.
- **Honest "What it doesn't catch" section** in the README.

## 4. Change / update / adapt

| Item | Why | Direction |
|---|---|---|
| `docs/roadmap.md` still lists v3.1/v3.2 as planned | Docs drift in the drift tool | Mark shipped; automate version references in the release workflow |
| README/docs pin `rev: v3.0.0` (v3.2.0 exists) | Same | Template the version or add a check (a `version` claim) |
| Scanner is line-based, one match per line, name-only | Cannot see command/flag/path claims | Introduce claims model (section 1) |
| `run_check()` has ~15 parameters | Hard to extend | Replace with a config dataclass shared by CLI, hook and Action |
| Only removed/signature-changed names are flagged; additions ignored | Fine for diff mode, wrong for verify mode | Keep diff mode; add separate `verify` mode |
| Rename = remove + add | Misses the most common doc breakage | Detect via normalized AST body hash |
| Hardcoded English noise blocklist | Fails on other-language docs and domain nouns | Keep default; make extension ergonomic (allowlist already exists) |
| `git.py` coverage was 57% at v3.0.1 **(verify)** | Real-world git edge cases live here | Add renames, deletes, binary, submodule, shallow-clone tests |
| `--noise-blocklist` vs `--noise-allowlist` | Two overlapping knobs | Document one primary path; keep both for compatibility |
| README broadening (3.1: CONTRIBUTING, docs/) **(verify)** | Check how targets are chosen and configured | Confirm defaults and the config key are documented |

## 5. Remove

- Stale roadmap text for shipped versions (collapse to a changelog-style list; the roadmap should hold only the future).
- Duplicate "deferred" lists that live in both roadmap and architecture docs.
- Untracked local artifacts from the working tree (`.coverage`, `site/`, caches) — confirm they are gitignored.
- The `.txt` and extension-less README names from default discovery *if* false positives are observed **(verify first)**.
- Backlog items that contradict the final scope (VS Code extension, `--fix`; see section 8).

## 6. Add — definitely

1. **Claims extractor** for fenced shell blocks and command-like inline spans (handle `$ ` prompts, `\` continuations, `&&`, placeholders, `<!-- readme-drift: ignore -->`).
2. **Repo-owned verifiers**: path existence, `make`, `npm run` / `yarn`, `docker compose` services and `-f`, `docker build --target`, `tox -e`, `pip install pkg[extra]`, `python -m` / script paths.
3. **Own-CLI flag verification** from click/argparse definitions (AST first; `--help` introspection later).
4. **`verify` mode** (full-README scan, not diff-driven) with the verified / broken / unverifiable states.
5. **Python code-block checks**: `ast.parse`, import resolution, call arguments vs. real signatures.
6. **Link and anchor checks** and **version-pin checks** (`rev:`, `requires-python`).
7. **Body-hash rename detection.**
8. **JSON output** (and optionally SARIF for CI annotations).
9. **Docs that say what is and is not verified**, per claim kind.
10. **A frozen public API** declaration and a non-goals page.

## 7. Add — optional

- Env var verification (`.env.example`, `os.environ` usage) — noisy; gated behind noise suppression.
- kubectl / helm checks limited to file existence, manifest names and `values.yaml` key paths.
- Migration/SQL file existence (`alembic`, `psql -f`); no database state.
- Execution tier: `make -n`, `docker compose config`, `--dry-run=client`, `--help`, only for blocks annotated `<!-- readme-drift: run -->`, CI-only.
- Optional `[semantic]` extra: bring-your-own LLM endpoint for prose claim extraction; advisory, warn-only, off by default.
- `.rst` claim parsing beyond what discovery already does.

## 8. Nice to have, but too much for a plugin

- VS Code / editor extension.
- `--fix` auto-editing or LLM-written README patches.
- Bundled model weights and a managed model lifecycle.
- A vector index of docs with incremental re-embedding.
- Hosted dashboard or history of doc health over time.

## 9. Out of scope

- Judging prose quality, tone, or completeness.
- Verifying third-party tool syntax (`docker`, `kubectl`, `git` flags).
- Live infrastructure or database state.
- Non-Python source languages (JS/TS, Go, Rust) via tree-sitter.
- Behavioural changes that do not alter names, signatures or config surface.
- Verifying external URLs (link rot) — use a dedicated link checker.
- Running arbitrary README commands by default.

---

## 10. Exit criteria for a v4.0 freeze

1. Claims model, owned-name verifiers (section 6, items 1–4) and `verify` mode shipped.
2. Python code-block and link/version checks shipped.
3. Body-hash rename detection shipped.
4. JSON output shipped; public API declared stable.
5. Docs and version references generated, not hand-edited; roadmap holds only the future.
6. Non-goals page published (sections 8 and 9).
7. Then maintenance only: dependency bumps and bug fixes.

## 11. Open decisions

- Is `verify` mode a new command or a flag on the existing one?
- Is the execution tier in or out for v4.0?
- Is the `[semantic]` extra built, or explicitly deferred?
- Which claim kinds are in the default set, and which are opt-in?
