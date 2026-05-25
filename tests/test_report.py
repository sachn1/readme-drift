"""Tests for report formatting."""

from pathlib import Path

from readme_drift.models import (
    ChangeType,
    DriftCheckResult,
    ReadmeMatch,
    StalenessFinding,
    SymbolChange,
)
from readme_drift.report import format_report


def _make_finding(
    symbol: str, change_type: ChangeType, line: int = 5
) -> StalenessFinding:
    change = SymbolChange(
        name=symbol,
        change_type=change_type,
        old_signature=f"{symbol}(x)"
        if change_type == ChangeType.SIGNATURE_CHANGED
        else None,
        new_signature=f"{symbol}(x, y)"
        if change_type == ChangeType.SIGNATURE_CHANGED
        else None,
    )
    match = ReadmeMatch(
        symbol=symbol,
        line_number=line,
        line_text=f"Use `{symbol}` to do things.",
        matched_text=f"`{symbol}`",
        readme_path=Path("README.md"),
    )
    return StalenessFinding(change=change, readme_matches=[match])


def test_passed_no_findings():
    result = DriftCheckResult(findings=[])
    assert result.passed
    assert "✅" in format_report(result)


def test_failed_with_findings():
    finding = _make_finding("Client.connect", ChangeType.SIGNATURE_CHANGED)
    result = DriftCheckResult(findings=[finding], readme_paths=[Path("README.md")])
    assert result.failed
    report = format_report(result)
    assert "❌" in report
    assert "Client.connect" in report


def test_skipped_result():
    result = DriftCheckResult(skipped=True, skip_reason="no Python files changed")
    assert result.passed
    assert "skipped" in format_report(result)


def test_report_shows_line_number():
    finding = _make_finding("helper", ChangeType.REMOVED, line=42)
    result = DriftCheckResult(findings=[finding], readme_paths=[Path("README.md")])
    report = format_report(result)
    assert "42" in report


def test_report_shows_update_hint():
    finding = _make_finding("func", ChangeType.REMOVED)
    result = DriftCheckResult(findings=[finding], readme_paths=[Path("README.md")])
    assert "update" in format_report(result).lower()


def test_report_multiple_findings():
    findings = [
        _make_finding("func_a", ChangeType.REMOVED),
        _make_finding("func_b", ChangeType.SIGNATURE_CHANGED),
    ]
    result = DriftCheckResult(findings=findings, readme_paths=[Path("README.md")])
    report = format_report(result)
    assert "func_a" in report
    assert "func_b" in report
    change = SymbolChange(
        name="foo",
        change_type=ChangeType.REMOVED,
        file="src/utils.py",
    )
    match = ReadmeMatch("foo", 10, "Use `foo` here.", "`foo`", Path("README.md"))
    finding = StalenessFinding(change=change, readme_matches=[match])
    result = DriftCheckResult(findings=[finding], readme_paths=[Path("README.md")])
    report = format_report(result)
    assert "src/utils.py" in report
