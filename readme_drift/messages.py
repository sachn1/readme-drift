"""User-facing message text, with no I/O and no display logic."""

PREFIX = "readme-drift:"

# -- Option-conflict warnings (stderr, always shown when the conflict exists) --

WARN_READMEPATHS_EXCLUDEDIRS = (
    "warning: --readme-paths disables discovery; --readme-exclude-dirs is ignored."
)
WARN_NO_PLAIN_TEXT_NOISE = (
    "warning: --no-plain-text-search disables plain-text matching; "
    "--noise-blocklist/--noise-allowlist have no effect."
)
WARN_BLOCKLIST_OVERRIDES_ALLOWLIST = (
    "warning: --noise-blocklist replaces the built-in list entirely; "
    "--noise-allowlist is ignored."
)

# -- --init status ------------------------------------------------------------


def init_refused(target: object) -> str:
    """Return the message shown when ``--init`` refuses to overwrite a README.

    Parameters
    ----------
    target : object
        Path of the existing README.

    Returns
    -------
    str
        Message text.
    """
    return f"README already exists and is not empty: {target}"


def init_created(target: object) -> str:
    """Return the message shown after ``--init`` creates a README.

    Parameters
    ----------
    target : object
        Path of the created README.

    Returns
    -------
    str
        Message text.
    """
    return f"Created {target}"


# -- Result report ------------------------------------------------------------


def report_skipped(reason: str) -> str:
    """Return the report line for a skipped run.

    Parameters
    ----------
    reason : str
        Why the run was skipped.

    Returns
    -------
    str
        Report text.
    """
    return f"{PREFIX} skipped ({reason})"


REPORT_PASSED = f"{PREFIX} ✅ No README staleness detected."
REPORT_FIX_ADVICE = "  → Please update the README or run with --no-verify to skip."
REPORT_FORCE_FLAGGED = "    (force-flagged via allowlist — not found in README)"


def report_failed_header(readme_label: str) -> str:
    """Return the header line of a failing report.

    Parameters
    ----------
    readme_label : str
        Comma-separated README file names.

    Returns
    -------
    str
        Header text.
    """
    return f"{PREFIX} ❌ {readme_label} may be stale:\n"


def report_verbose_header() -> str:
    """Return the header line of the verbose log block.

    Returns
    -------
    str
        Header text.
    """
    return f"{PREFIX} verbose log:\n"


def suppressed_hint(count: int) -> str:
    """Return the hint about noise-suppressed plain-text matches.

    Parameters
    ----------
    count : int
        Number of changed symbols that were noise-suppressed.

    Returns
    -------
    str
        Hint text.
    """
    noun = "symbols" if count != 1 else "symbol"
    verb = "were" if count != 1 else "was"
    return (
        f"{PREFIX} ℹ {count} changed {noun} "
        f"matched the README as plain text but {verb} noise-suppressed "
        "(no backtick match) — run with --verbose for details."
    )


# -- First-use tip (stderr, shown once per repo) ------------------------------

BACKTICK_TIP = f"""\
{PREFIX} 💡 First run in this repository — one tip for accurate results.

  Wrap commands, function/class names, config keys, flags and file paths in
  backticks in your README, e.g. `make lint`, `Client.connect`, `--warn-only`.
  This is good documentation practice, and it is what lets readme-drift match
  a changed name precisely instead of guessing from plain prose.

  This message is shown once per repository. Silence it with
  `tips = false` under [tool.readme-drift] or README_DRIFT_NO_TIPS=1."""
