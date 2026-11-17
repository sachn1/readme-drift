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


# -- Claim verification (--verify) --------------------------------------------

VERIFY_NO_CLAIMS = f"{PREFIX} verify: no shell commands found in README code blocks or inline code spans."
VERIFY_FIX_ADVICE = (
    "  → Fix the README, or put <!-- readme-drift: ignore --> above a command "
    "that is intentionally different."
)


def verify_passed(verified: int, unverifiable: int) -> str:
    """Return the report line for a verify run with no broken claims.

    Parameters
    ----------
    verified : int
        Number of verified claims.
    unverifiable : int
        Number of claims that could not be verified.

    Returns
    -------
    str
        Report text.
    """
    return (
        f"{PREFIX} ✅ verify: {verified} README command check(s) verified, "
        f"none broken ({unverifiable} unverifiable — run with --verbose to list)."
    )


def verify_failed_header(broken: int) -> str:
    """Return the header line of a failing verify report.

    Parameters
    ----------
    broken : int
        Number of broken claims.

    Returns
    -------
    str
        Header text.
    """
    return (
        f"{PREFIX} ❌ verify: {broken} README command check(s) do not match the repo:\n"
    )


def verify_counts(verified: int, broken: int, unverifiable: int) -> str:
    """Return the one-line tally of claim outcomes.

    Parameters
    ----------
    verified : int
        Number of verified claims.
    broken : int
        Number of broken claims.
    unverifiable : int
        Number of unverifiable claims.

    Returns
    -------
    str
        Tally text.
    """
    return f"  verified: {verified} · broken: {broken} · unverifiable: {unverifiable}"


def verify_verbose_header() -> str:
    """Return the header line of the verify verbose listing.

    Returns
    -------
    str
        Header text.
    """
    return f"{PREFIX} verify: all checks:\n"


def verify_claim_lines(
    raw: str, readme_name: str, line_number: int, reason: str
) -> list[str]:
    """Return the two report lines describing one broken claim.

    Parameters
    ----------
    raw : str
        The command as written in the README.
    readme_name : str
        File name of the README.
    line_number : int
        Line of the command in the README.
    reason : str
        Why the claim is broken.

    Returns
    -------
    list[str]
        The command line and its location-and-reason line.
    """
    return [f"  • `{raw}`", f"    in {readme_name} line {line_number}: {reason}"]


def verify_verbose_line(
    status: str, raw: str, readme_name: str, line_number: int, reason: str
) -> str:
    """Return one line of the verify verbose listing.

    Parameters
    ----------
    status : str
        Outcome label (verified, broken or unverifiable).
    raw : str
        The command as written in the README.
    readme_name : str
        File name of the README.
    line_number : int
        Line of the command in the README.
    reason : str
        Reason for the outcome.

    Returns
    -------
    str
        Listing line.
    """
    return f"  [{status}] `{raw}` ({readme_name}:{line_number}) — {reason}"


# Reasons attached to each claim outcome. ``{name}`` style fields are filled in
# with ``str.format`` by the verifiers.
REASON_CWD_CHANGED = "working directory was changed earlier in this block"
REASON_NO_VERIFIER = "no verifier for '{head}'"
REASON_NOTHING = "nothing repo-owned to verify"
REASON_PATH_OK = "path '{path}' exists"
REASON_PATH_MISSING = "path '{path}' does not exist"
REASON_PATH_OUTSIDE = "'{path}' is outside the repository"
REASON_PATH_GENERATED = "'{path}' is in a generated directory"
REASON_MAKE_OK = "make target '{name}' is defined in {file}"
REASON_MAKE_MISSING = "make target '{name}' not found in {file}"
REASON_MAKE_UNCERTAIN = (
    "make target '{name}' may come from an include or variable in {file}"
)
REASON_MAKE_ALT = "make is pointed at another directory or makefile"
REASON_MAKE_NO_FILE = "no Makefile in the repository root"
REASON_JS_OK = "script '{name}' is defined in package.json"
REASON_JS_MISSING = "script '{name}' not found in package.json"
REASON_JS_MAYBE = "'{name}' is not a package.json script; it may be a {tool} command"
REASON_JS_NO_FILE = "no package.json in the repository root"
REASON_JS_NOT_SCRIPT = "not a script invocation"
REASON_JS_ALT = "package manager is pointed at another directory or workspace"
REASON_COMPOSE_OK = "service '{name}' is defined in {file}"
REASON_COMPOSE_MISSING = "service '{name}' not found in {file}"
REASON_COMPOSE_UNCERTAIN = "service '{name}' may come from an included compose file"
REASON_COMPOSE_NO_FILE = "no compose file found"
REASON_COMPOSE_NOT_COMPOSE = "not a compose command"
REASON_COMPOSE_NO_SERVICES = "subcommand '{sub}' names no services"
REASON_CLI_OK = "'{head}' defines option {flag}"
REASON_CLI_MISSING = "'{head}' has no option {flag}"
REASON_CLI_UNREADABLE = "could not read the options of '{head}' statically"
REASON_CLI_SUBCOMMAND = (
    "option {flag} follows a subcommand of '{head}'; subcommand options are not read"
)
REASON_PY_MODULE_OK = "module '{module}' found in the repository"
REASON_PY_MODULE_MISSING = "module '{module}' not found in the repository"
REASON_PY_MODULE_EXTERNAL = "'{module}' is not a module of this repository"
REASON_PY_INLINE = "inline code is not verified"


# -- First-use tip (stderr, shown once per repo) ------------------------------

BACKTICK_TIP = f"""\
{PREFIX} 💡 First run in this repository — one tip for accurate results.

  Wrap commands, function/class names, config keys, flags and file paths in
  backticks in your README, e.g. `make lint`, `Client.connect`, `--warn-only`.
  This is good documentation practice, and it is what lets readme-drift match
  a changed name precisely instead of guessing from plain prose.

  This message is shown once per repository. Silence it with
  `tips = false` under [tool.readme-drift] or README_DRIFT_NO_TIPS=1."""


def survived_log(name: str) -> str:
    """Return the verbose line for a removed config key whose name lives on.

    Parameters
    ----------
    name : str
        The removed key.

    Returns
    -------
    str
        Log line text.
    """
    return f"{name} [removed] -> name still appears in the new file -> skipped"
