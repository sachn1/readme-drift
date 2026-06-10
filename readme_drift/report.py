"""Format check results into human-readable reports."""

from .models import DriftCheckResult


def format_report(result: DriftCheckResult) -> str:
    """Format a CheckResult into a human-readable string."""
    lines: list[str] = []

    if result.skipped:
        return f"readme-drift: skipped ({result.skip_reason})"

    if not result.findings:
        report = "readme-drift: ✅ No README staleness detected."
        if result.verbose_log:
            report += "\n\nreadme-drift: verbose log:\n" + "\n".join(
                f"  {entry}" for entry in result.verbose_log
            )
        return report

    readme_label = ", ".join(sorted({p.name for p in result.readme_paths})) or "README"
    lines.append(f"readme-drift: ❌ {readme_label} may be stale:\n")

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

    if result.verbose_log:
        lines.append("\nreadme-drift: verbose log:")
        for entry in result.verbose_log:
            lines.append(f"  {entry}")

    return "\n".join(lines)
