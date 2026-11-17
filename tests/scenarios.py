"""Scenario definitions shared by the scenario tests and the doc image generator."""

import subprocess
from pathlib import Path

from readme_drift.constants import DEFAULT_NOISE_BLOCKLIST
from readme_drift.drift_checker import run_check
from readme_drift.models import DriftCheckResult, VerifyResult
from readme_drift.verify import run_verify

PY_CONNECT = "def connect(host, port):\n    pass\n"
CLASS_DIAGRAM = (
    "```mermaid\nclassDiagram\n    class Client {\n"
    "        +connect()\n        +run()\n    }\n```\n"
)
FLOWCHART = "```mermaid\nflowchart LR\n    A[Client] --> B[run]\n```\n"
NO_BUILD = [w for w in DEFAULT_NOISE_BLOCKLIST if w != "build"]
FENCE = "`" * 3

# id: (old files, new files, README before [, README after], run_check kwargs,
#      expected flagged (name, change type) list, expected suppressed-hint count)
SCENARIOS = {
    # -- Python: caught ---------------------------------------------------------
    "py-rename": (
        {"client.py": PY_CONNECT},
        {"client.py": "def open_session(host, port):\n    pass\n"},
        ["Call `connect(host, port)` to open a session.\n"],
        {},
        [("connect", "removed")],
        0,
    ),
    "py-signature-change": (
        {"client.py": "class Client:\n    def connect(self, host, port): pass\n"},
        {"client.py": "class Client:\n    def connect(self, url): pass\n"},
        ["Use `Client.connect(host, port)`.\n"],
        {},
        [("Client.connect", "signature_changed")],
        0,
    ),
    "py-class-removed": (
        {"client.py": "class Widget:\n    pass\n"},
        {"client.py": "x = 1\n"},
        ["The `Widget` class renders.\n"],
        {},
        [("Widget", "removed")],
        0,
    ),
    "py-default-changed": (
        {"client.py": "def retry(count=3): pass\n"},
        {"client.py": "def retry(count=5): pass\n"},
        ["`retry` tries 3 times.\n"],
        {},
        [("retry", "signature_changed")],
        0,
    ),
    "py-prose-long-name": (
        {"client.py": PY_CONNECT},
        {"client.py": "x = 1\n"},
        ["Call connect to open a session.\n"],
        {},
        [("connect", "removed")],
        0,
    ),
    "py-code-block-example": (
        {"client.py": PY_CONNECT},
        {"client.py": "x = 1\n"},
        ["```python\nclient.connect('h', 1)\n```\n"],
        {},
        [("connect", "removed")],
        0,
    ),
    "py-private-with-flag": (
        {"client.py": "def _helper(): pass\n"},
        {"client.py": "def _util(): pass\n"},
        ["Uses `_helper`.\n"],
        {"include_private": True},
        [("_helper", "removed")],
        0,
    ),
    "py-noise-word-backticked": (
        {"client.py": "def run(): pass\n"},
        {"client.py": "x = 1\n"},
        ["Use `run` to start it.\n"],
        {},
        [("run", "removed")],
        0,
    ),
    "py-readme-updated-too": (
        {"client.py": PY_CONNECT},
        {"client.py": "def open_session(host, port): pass\n"},
        ["Call `connect(host, port)`.\n", "Call `open_session(host, port)`.\n"],
        {},
        [],
        0,
    ),
    # -- Python: not caught -----------------------------------------------------
    "py-function-added": (
        {"client.py": "x = 1\n"},
        {"client.py": "def export(): pass\n"},
        ["Nothing about it.\n"],
        {},
        [],
        0,
    ),
    "py-body-only-change": (
        {"client.py": "def fetch(url):\n    return 1\n"},
        {"client.py": "def fetch(url):\n    return 2\n"},
        ["`fetch` returns a sorted list.\n"],
        {},
        [],
        0,
    ),
    "py-private-default": (
        {"client.py": "def _helper(): pass\n"},
        {"client.py": "def _util(): pass\n"},
        ["Uses `_helper`.\n"],
        {},
        [],
        0,
    ),
    "py-symbol-not-in-readme": (
        {"client.py": PY_CONNECT},
        {"client.py": "x = 1\n"},
        ["Unrelated text.\n"],
        {},
        [],
        0,
    ),
    "py-noise-word-prose": (
        {"client.py": "def run(): pass\n"},
        {"client.py": "x = 1\n"},
        ["Use run to start it.\n"],
        {},
        [],
        1,
    ),
    "py-short-name-prose": (
        {"client.py": "def go(): pass\n"},
        {"client.py": "x = 1\n"},
        ["Just go.\n"],
        {},
        [],
        1,
    ),
    # -- Config and build files: caught -----------------------------------------
    "config-npm-script-removed": (
        {"package.json": '{"scripts": {"lint-docs": "x"}}'},
        {"package.json": '{"scripts": {}}'},
        ["Run `npm run lint-docs`.\n"],
        {},
        [("lint-docs", "removed")],
        0,
    ),
    "config-tool-section-removed": (
        {"pyproject.toml": "[tool.black]\nline-length = 88\n"},
        {"pyproject.toml": "[tool.ruff]\nline-length = 88\n"},
        ["We format with black.\n"],
        {},
        [("black", "removed")],
        0,
    ),
    "config-ci-job-renamed": (
        {"ci.yml": "jobs:\n  integration:\n    runs-on: ubuntu-latest\n"},
        {"ci.yml": "jobs:\n  e2e:\n    runs-on: ubuntu-latest\n"},
        ["The `integration` job runs nightly.\n"],
        {},
        [("integration", "removed")],
        0,
    ),
    "makefile-target-removed": (
        {"Makefile": "deploy:\n\techo\n"},
        {"Makefile": "other:\n\techo\n"},
        ["Run `make deploy` to ship.\n"],
        {},
        [("deploy", "removed")],
        0,
    ),
    # -- Config and build files: not caught -------------------------------------
    "config-value-changed": (
        {"c.yml": "port: 8080\n"},
        {"c.yml": "port: 9090\n"},
        ["The default port is 8080.\n"],
        {},
        [],
        0,
    ),
    "config-npm-build-removed": (
        {"package.json": '{"scripts": {"build": "x"}}'},
        {"package.json": '{"scripts": {}}'},
        ["Run `npm run build`.\n"],
        {},
        [],
        1,
    ),
    "makefile-build-removed": (
        {"Makefile": "build:\n\techo\n"},
        {"Makefile": "package:\n\techo\n"},
        ["Run `make build` to package it.\n"],
        {},
        [],
        1,
    ),
    "makefile-lint-removed": (
        {"Makefile": "lint:\n\techo\n"},
        {"Makefile": "other:\n\techo\n"},
        ["Run `make lint`.\n"],
        {},
        [],
        1,
    ),
    # -- Workarounds for noise-listed command names -----------------------------
    "fix-noise-allowlist": (
        {"Makefile": "build:\n\techo\n"},
        {"Makefile": "other:\n\techo\n"},
        ["Run `make build` to compile.\n"],
        {"noise_blocklist": NO_BUILD},
        [("build", "removed")],
        0,
    ),
    "fix-symbol-allowlist": (
        {"Makefile": "build:\n\techo\n"},
        {"Makefile": "other:\n\techo\n"},
        ["Run `make build` to compile.\n"],
        {"symbol_allowlist": ["build"]},
        [("build", "removed")],
        0,
    ),
    "fix-noise-disabled": (
        {"Makefile": "build:\n\techo\n"},
        {"Makefile": "other:\n\techo\n"},
        ["Run `make build` to compile.\n"],
        {"noise_blocklist": []},
        [("build", "removed")],
        0,
    ),
    # -- Known false positives --------------------------------------------------
    "false-positive-backtick-prefix": (
        {"client.py": PY_CONNECT},
        {"client.py": "x = 1\n"},
        ["See `connection_pool` for pooling.\n"],
        {},
        [("connect", "removed")],
        0,
    ),
    # -- Mermaid ----------------------------------------------------------------
    "mermaid-class-renamed": (
        {"client.py": "class Client:\n    pass\n"},
        {"client.py": "class Session:\n    pass\n"},
        [CLASS_DIAGRAM],
        {},
        [("Client", "removed")],
        0,
    ),
    "mermaid-class-diagram-short-name": (
        {"client.py": "class Client:\n    def run(self): pass\n"},
        {"client.py": "class Client:\n    pass\n"},
        [CLASS_DIAGRAM],
        {},
        [("Client.run", "removed")],
        0,
    ),
    "mermaid-method-of-another-class": (
        {"client.py": "class Job:\n    def run(self): pass\n"},
        {"client.py": "class Job:\n    pass\n"},
        [CLASS_DIAGRAM],
        {},
        [],
        0,
    ),
    "mermaid-flowchart-long-name": (
        {"client.py": "class Client:\n    pass\n"},
        {"client.py": "x = 1\n"},
        [FLOWCHART],
        {},
        [("Client", "removed")],
        0,
    ),
    "mermaid-flowchart-short-name": (
        {"client.py": "def run(): pass\n"},
        {"client.py": "x = 1\n"},
        [FLOWCHART],
        {},
        [],
        1,
    ),
    # -- Out of scope -----------------------------------------------------------
    "out-of-scope-other-doc": (
        {"client.py": PY_CONNECT, "CONTRIBUTING.md": "Use `connect`.\n"},
        {"client.py": "x = 1\n"},
        ["Unrelated.\n"],
        {},
        [],
        0,
    ),
}


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in a directory, failing on error."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def run_scenario(name: str, root: Path) -> DriftCheckResult:
    """Build the scenario's repository under root and run the real check on it."""
    old, new, readme, kwargs, _expected, _hint = SCENARIOS[name]
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    for rel, text in old.items():
        (root / rel).write_text(text)
    (root / "README.md").write_text(readme[0])
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "initial")
    for rel, text in new.items():
        (root / rel).write_text(text)
    (root / "README.md").write_text(readme[-1])
    return run_check(base_ref="HEAD", repo_root=root, **kwargs)


# id: (repo files, README text, expected (status, command) per check in README order).
# These run `--verify`: a full scan of the README commands against the repository.
VERIFY_SCENARIOS = {
    "verify-make-build": (
        {"Makefile": "lint:\n\techo lint\ntest:\n\techo test\n"},
        "# Demo\n\nRun `make build` to package it.\n\n"
        f"{FENCE}bash\nmake lint\nmake build\n{FENCE}\n",
        [
            ("broken", "make build"),
            ("verified", "make lint"),
            ("broken", "make build"),
        ],
    ),
    "verify-code-block": (
        {
            "Makefile": "lint:\n\techo lint\ntest:\n\techo test\n",
            "package.json": '{"scripts": {"lint-docs": "echo docs"}}',
            "docker-compose.yml": "services:\n  web:\n    image: nginx\n",
            "scripts/deploy.sh": "echo deploy\n",
        },
        f"{FENCE}bash\nmake lint test\nnpm run lint-docs && npm run publish\n"
        f"docker compose up web db\nbash scripts/deploy.sh\n{FENCE}\n",
        [
            ("verified", "make lint test"),
            ("verified", "make lint test"),
            ("verified", "npm run lint-docs"),
            ("broken", "npm run publish"),
            ("verified", "docker compose up web db"),
            ("broken", "docker compose up web db"),
            ("verified", "bash scripts/deploy.sh"),
        ],
    ),
    "verify-unverifiable": (
        {"Makefile": "lint:\n\techo lint\n"},
        f"{FENCE}bash\nmake <target>\ncd app && make anything\n{FENCE}\n\n"
        f"<!-- readme-drift: ignore -->\n{FENCE}bash\nmake intentionally-missing\n{FENCE}\n",
        [
            ("unverifiable", "make"),
            ("unverifiable", "cd app"),
            ("unverifiable", "make anything"),
        ],
    ),
}


def run_verify_scenario(name: str, root: Path) -> VerifyResult:
    """Build a verify scenario's repository under root and run the real verification."""
    files, readme, _expected = VERIFY_SCENARIOS[name]
    _git(root, "init", "-q")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "README.md").write_text(readme)
    return run_verify(repo_root=root)
