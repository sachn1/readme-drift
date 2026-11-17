# How it works in practice

Each image is generated from a real run of the tool. A test fails if one goes stale.

![Rename a function: caught](assets/scenarios/py-rename.svg)

![Rename a CI job: caught](assets/scenarios/config-ci-job-renamed.svg)

![Rename a class shown in a mermaid diagram: caught](assets/scenarios/mermaid-class-renamed.svg)

## What the default check does not catch

![Change behaviour, keep the signature: not tracked](assets/scenarios/py-body-only-change.svg)

## Check the commands too: `--verify`

The default check reacts to names that changed in your diff. `--verify` reads the commands in your README, in code blocks and in sentences, and checks them against what the repo defines.

![A command in a sentence and in a code block: caught with --verify](assets/scenarios/verify-make-build.svg)

![Every command in a code block: caught with --verify](assets/scenarios/verify-code-block.svg)

![When it is not sure, it does not fail](assets/scenarios/verify-unverifiable.svg)
