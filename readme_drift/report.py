"""Format check results into human-readable reports."""

from .models import DriftCheckResult


def _suppressed_hint(result: DriftCheckResult) -> str:
    """Low-noise hint for symbols that matched the README as plain text but
    were noise-suppressed to backtick-only matching, so no finding fired.

    Only rendered when non-empty — most runs never hit this case.
    """
    if not result.suppressed_hint_count:
        return ""
    plural = result.suppressed_hint_count != 1
    noun = "symbols" if plural else "symbol"
    verb = "were" if plural else "was"
    return (
        f"readme-drift: ℹ {result.suppressed_hint_count} changed {noun} "
        f"matched the README as plain text but {verb} noise-suppressed "
        "(no backtick match) — run with --verbose for details."
    )


def _verbose_block(result: DriftCheckResult) -> str:
    if not result.verbose_log:
        return ""
    return "readme-drift: verbose log:\n" + "\n".join(
        f"  {entry}" for entry in result.verbose_log
    )


def _passing_report(result: DriftCheckResult) -> str:
    report = "readme-drift: ✅ No README staleness detected."
    if hint := _suppressed_hint(result):
        report += "\n" + hint
    if verbose := _verbose_block(result):
        report += "\n\n" + verbose
    return report


def _failing_report(result: DriftCheckResult) -> str:
    readme_label = ", ".join(sorted({p.name for p in result.readme_paths})) or "README"
    lines: list[str] = [f"readme-drift: ❌ {readme_label} may be stale:\n"]

    for finding in result.findings:
        change = finding.change
        lines.append(f"  • {change}")
        if change.file:
            lines.append(f"    in {change.file}")
        if finding.readme_matches:
            for match in finding.readme_matches:
                lines.append(
                    f"    referenced in {match.readme_path.name} line {match.line_number}: "
                    f"…{match.line_text}…"
                )
        else:
            lines.append("    (force-flagged via allowlist — not found in README)")
        lines.append("")

    lines.append("  → Please update the README or run with --no-verify to skip.")

    if hint := _suppressed_hint(result):
        lines.append(hint)

    if verbose := _verbose_block(result):
        lines.append("\n" + verbose)

    return "\n".join(lines)


def format_report(result: DriftCheckResult) -> str:
    """Format a CheckResult into a human-readable string."""
    if result.skipped:
        return f"readme-drift: skipped ({result.skip_reason})"

    if not result.findings:
        return _passing_report(result)

    return _failing_report(result)
