# How it works in practice

Each image is generated from a real run of the tool. A test fails if one goes stale.

![Rename a function: caught](assets/scenarios/py-rename.svg)

![Remove a Makefile target: caught](assets/scenarios/makefile-target-removed.svg)

![Rename a class shown in a mermaid diagram: caught](assets/scenarios/mermaid-class-renamed.svg)

## What it does not catch

![Change behaviour, keep the signature: not tracked](assets/scenarios/py-body-only-change.svg)

![The build target is removed but the README still says make build: missed, known gap](assets/scenarios/makefile-build-removed.svg)

Fix: `--noise-allowlist build`, or give the bare name its own backtick span.

![Remove connect, README mentions connection_pool: false alarm, known gap](assets/scenarios/false-positive-backtick-prefix.svg)

Fix: `symbol-denylist = ["connect"]`.
