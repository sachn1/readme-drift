"""Format check results into human-readable reports."""

from .models import CheckResult


def format_report(result: CheckResult) -> str:
    """Format a CheckResult into a human-readable string."""
    lines: list[str] = []

    if result.skipped:
        return f"readme-check: skipped ({result.skip_reason})"

    if result.readme_was_updated:
        return "readme-check: ✅ README was updated alongside code changes."

    if not result.findings:
        return "readme-check: ✅ No README staleness detected."

    readme_label = ", ".join(sorted({p.name for p in result.readme_paths})) or "README"
    lines.append(f"readme-check: ❌ {readme_label} may be stale:\n")

    for finding in result.findings:
        change = finding.change
        lines.append(f"  • {change}")
        if change.file:
            lines.append(f"    in {change.file}")
        for match in finding.readme_matches:
            lines.append(
                f"    referenced in {match.readme_path.name} line {match.line_number}: "
                f"…{match.line_text}…"
            )
        lines.append("")

    lines.append("  → Please update the README or run with --no-verify to skip.")

    return "\n".join(lines)
