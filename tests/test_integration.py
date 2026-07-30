"""Integration tests: full pipeline wired without git dependency."""

from readme_drift.ast_diff import diff_apis
from readme_drift.config_diff import diff_config
from readme_drift.drift_checker import _symbols_from_changes
from readme_drift.models import ChangeType, DriftCheckResult, StalenessFinding
from readme_drift.report import format_report
from readme_drift.scanner import scan_readme_for_symbols


def _run_pipeline(
    old_source,
    new_source,
    readme_text,
    tmp_path,
    *,
    is_config=False,
    filename="client.py",
):
    readme = tmp_path / "README.md"
    readme.write_text(readme_text)

    if is_config:
        changes = diff_config(old_source, new_source, file=filename)
    else:
        changes = diff_apis(old_source, new_source, file=filename)

    symbols = _symbols_from_changes(changes)
    readme_matches = scan_readme_for_symbols(readme, symbols)

    findings = [
        StalenessFinding(change=c, readme_matches=readme_matches[c.name])
        for c in changes
        if c.change_type != ChangeType.ADDED and c.name in readme_matches
    ]
    return DriftCheckResult(findings=findings, readme_paths=[readme])


def test_signature_change_flagged(tmp_path):
    old = "class Client:\n    def connect(self, host, port): ...\n"
    new = "class Client:\n    def connect(self, url): ...\n"
    readme = "Call `Client.connect(host, port)` to open a connection."

    result = _run_pipeline(old, new, readme, tmp_path)

    assert result.failed
    assert any(f.symbol == "Client.connect" for f in result.findings)
    assert "❌" in format_report(result)


def test_removed_symbol_in_readme(tmp_path):
    old = "class Client:\n    def connect(self, host, port): ...\n"
    new = ""
    readme = (
        "Use the `Client` class to connect.\nCall `Client.connect(host, port)` first."
    )

    result = _run_pipeline(old, new, readme, tmp_path)

    assert result.failed
    assert any(f.symbol == "Client" for f in result.findings)


def test_removed_symbol_not_in_readme(tmp_path):
    old = "def _obscure_internal(): ...\n"
    new = ""
    readme = "# Hello world\nNo code references here.\n"

    result = _run_pipeline(old, new, readme, tmp_path)

    assert result.passed


def test_config_removed_key_in_readme(tmp_path):
    old = '{"scripts": {"build": "tsc", "test": "jest"}}'
    new = '{"scripts": {"test": "jest"}}'
    readme = "Run `npm run build` to compile the project."

    result = _run_pipeline(
        old, new, readme, tmp_path, is_config=True, filename="package.json"
    )

    assert result.failed
    assert any(f.symbol == "build" for f in result.findings)


def test_added_symbol_never_stale(tmp_path):
    old = ""
    new = "class Client:\n    def connect(self, host, port): ...\n"
    readme = "Use the `Client` class.\nCall `Client.connect(host, port)` to open a connection."

    result = _run_pipeline(old, new, readme, tmp_path)

    assert result.passed


def test_makefile_removed_target_in_readme(tmp_path):
    old = "build:\n\tgo build ./...\n\ndeploy:\n\t./deploy.sh\n"
    new = "build:\n\tgo build ./...\n"
    readme = "Run `make deploy` to ship to production."

    result = _run_pipeline(
        old, new, readme, tmp_path, is_config=True, filename="Makefile"
    )

    assert result.failed
    assert any(f.symbol == "deploy" for f in result.findings)
