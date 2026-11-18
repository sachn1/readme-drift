# Real-world benchmark

> **Status: research / work in progress.** This branch holds an investigation, not a finished feature. The seven fix commits under the claims PR are a prototype used to
> measure what each change does on real repositories; they are not proposed for merging yet. Results are kept locally in `benchmarks/results/` (gitignored), so re-run the
> benchmark to regenerate them. Section 8 of the notebook compares versions on whichever repositories each one ran, so compare like with like. Headline numbers so far
> (3 repositories, baseline versus all seven fixes): diff-mode findings 60 to 20 (false alarms 50 to 5), docs what-if findings 38 to 11, `--verify` false alarms 5 to 3,
> injected drift caught 14 to 15 of 20. Zero useful diff-mode findings before or after, so recall on natural drift is still unmeasured.

Runs `readme-drift` against popular open-source repositories and records where it helps, where it raises false alarms, and where it misses.
Needs network access and a few hundred MB of disk, so it is **not** part of `make check` or CI.

| File | Purpose |
|---|---|
| `run_benchmark.py` | Clones each repository and runs every phase: `--verify`, history replay, injected drift, docs what-if and the real `pre-commit` hook. Writes one JSON file per repository. |
| `triage.py` | Labels findings (useful or false alarm, with a cause) from evidence the runner records, and computes the headline metrics. |
| `analysis.ipynb` | Reads the results and shows the tables. The committed copy has outputs, so it is readable as a report. |
| `execute_notebook.py` | Re-runs the notebook against the current results and stores the outputs. |

## Run it

```bash
# 1. measure the tool in this checkout (use a clean clone of it for --hook-repo)
poetry run python benchmarks/run_benchmark.py \
    --workdir /tmp/bench/repos --results benchmarks/results/baseline \
    --hook-repo /path/to/clean/readme-drift/clone --precommit-path /path/to/pre_commit

# 2. measure another version of the tool by pointing PYTHONPATH at its checkout
PYTHONPATH=/path/to/other/checkout poetry run python benchmarks/run_benchmark.py \
    --workdir /tmp/bench/repos --results benchmarks/results/fixed \
    --phases verify replay inject replay_docs

# 3. refresh the report; the notebook compares every folder under benchmarks/results/
poetry run python benchmarks/execute_notebook.py
```

`--only owner/name ...` limits the run to some repositories, and `--phases` to some phases.
Install `pre-commit` somewhere importable (for example `pip install --target DIR pre-commit`) and pass that directory as `--precommit-path`.

## How to read the numbers

- **Useful** means a maintainer would plausibly want the warning. **False alarm** means they would not. Labels come from deterministic rules in `triage.py`
  plus a short list of manual judgements (`MANUAL`). Anything undecided is reported as *unlabeled*, never counted silently.
- **Injected drift** has a known right answer, so it measures recall. Real drift is rare in well-maintained repositories, so replaying history mostly measures precision.
- Cloned code is untrusted input. The tool parses it statically and never executes it.
