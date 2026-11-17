"""Format check results into human-readable reports."""

from . import messages
from .models import ClaimResult, ClaimStatus, DriftCheckResult, VerifyResult


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


def _claim_lines(item: ClaimResult) -> list[str]:
    """Format one broken claim as a bullet with its location and reason."""
    claim = item.claim
    return messages.verify_claim_lines(
        claim.raw, claim.readme_path.name, claim.line_number, item.reason
    )


def _count(result: VerifyResult, status: ClaimStatus) -> int:
    """Count results with a given status."""
    return sum(1 for r in result.results if r.status is status)


def format_verify_report(result: VerifyResult, *, verbose: bool = False) -> str:
    """Format a claim-verification result into a human-readable report.

    Parameters
    ----------
    result : VerifyResult
        Result of verifying README commands.
    verbose : bool, optional
        List every check, not only the broken ones, by default False.

    Returns
    -------
    str
        Report text for the no-commands, passing or failing outcome.
    """
    if not result.results:
        return messages.VERIFY_NO_CLAIMS

    verified = _count(result, ClaimStatus.VERIFIED)
    broken = _count(result, ClaimStatus.BROKEN)
    unverifiable = _count(result, ClaimStatus.UNVERIFIABLE)

    lines: list[str] = []
    if result.passed:
        lines.append(messages.verify_passed(verified, unverifiable))
    else:
        lines.append(messages.verify_failed_header(broken))
        for item in result.broken:
            lines.extend(_claim_lines(item))
            lines.append("")
        lines.append(messages.verify_counts(verified, broken, unverifiable))
        lines.append(messages.VERIFY_FIX_ADVICE)

    if verbose:
        lines.append("")
        lines.append(messages.verify_verbose_header().rstrip("\n"))
        for item in result.results:
            claim = item.claim
            lines.append(
                messages.verify_verbose_line(
                    item.status.value,
                    claim.raw,
                    claim.readme_path.name,
                    claim.line_number,
                    item.reason,
                )
            )
    return "\n".join(lines)
