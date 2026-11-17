"""Format check results into human-readable reports."""

from . import messages
from .models import DriftCheckResult


def _suppressed_hint(result: DriftCheckResult) -> str:
    """Return the noise-suppression hint, or an empty string when not applicable."""
    if not result.suppressed_hint_count:
        return ""
    return messages.suppressed_hint(result.suppressed_hint_count)


def _verbose_block(result: DriftCheckResult) -> str:
    """Return the verbose log block, or an empty string when empty."""
    if not result.verbose_log:
        return ""
    return messages.report_verbose_header() + "\n".join(
        f"  {entry}" for entry in result.verbose_log
    )


def _passing_report(result: DriftCheckResult) -> str:
    """Format the report for a run with no findings."""
    report = messages.REPORT_PASSED
    if hint := _suppressed_hint(result):
        report += "\n" + hint
    if verbose := _verbose_block(result):
        report += "\n\n" + verbose
    return report


def _failing_report(result: DriftCheckResult) -> str:
    """Format the report for a run with findings."""
    readme_label = ", ".join(sorted({p.name for p in result.readme_paths})) or "README"
    lines: list[str] = [messages.report_failed_header(readme_label)]

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
            lines.append(messages.REPORT_FORCE_FLAGGED)
        lines.append("")

    lines.append(messages.REPORT_FIX_ADVICE)

    if hint := _suppressed_hint(result):
        lines.append(hint)

    if verbose := _verbose_block(result):
        lines.append("\n" + verbose)

    return "\n".join(lines)


def format_report(result: DriftCheckResult) -> str:
    """Format a check result into a human-readable report.

    Parameters
    ----------
    result : DriftCheckResult
        Result of a drift check.

    Returns
    -------
    str
        Report text for the skipped, passing or failing outcome.
    """
    if result.skipped:
        return messages.report_skipped(result.skip_reason)

    if not result.findings:
        return _passing_report(result)

    return _failing_report(result)
