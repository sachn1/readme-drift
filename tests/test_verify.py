"""Tests for the end-to-end README command verification run."""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from readme_drift.cli import main
from readme_drift.drift_checker import resolve_readmes
from readme_drift.models import (
    Claim,
    ClaimResult,
    ClaimStatus,
    VerifyResult,
)
from readme_drift.report import format_verify_report
from readme_drift.verify import run_verify


def _repo(tmp_path, readme):
    """Create a git repo with a Makefile and the given README text."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "Makefile").write_text("lint:\n\techo\n")
    (tmp_path / "README.md").write_text(readme)
    return tmp_path


def _result(status, raw="make x", reason="why"):
    """Build a ClaimResult for a command at README.md line 3."""
    claim = Claim(
        head=raw.split()[0],
        args=tuple(raw.split()[1:]),
        raw=raw,
        readme_path=Path("README.md"),
        line_number=3,
    )
    return ClaimResult(claim, status, reason)


# --- run_verify --------------------------------------------------------------


def test_run_verify_passes_when_commands_match(tmp_path):
    """Commands that resolve against the repo produce a passing result."""
    root = _repo(tmp_path, "```bash\nmake lint\n```\n")
    result = run_verify(repo_root=root)
    assert result.passed
    assert [r.status for r in result.results] == [ClaimStatus.VERIFIED]


def test_run_verify_flags_broken_command(tmp_path):
    """A command that no longer matches the repo fails."""
    root = _repo(tmp_path, "```bash\nmake lint\nmake docs\n```\n")
    result = run_verify(repo_root=root)
    assert result.failed
    assert [r.claim.raw for r in result.broken] == ["make docs"]


def test_run_verify_honours_explicit_readme_paths(tmp_path):
    """readme_paths limits the scan to the named files."""
    root = _repo(tmp_path, "```bash\nmake docs\n```\n")
    (root / "OTHER.md").write_text("```bash\nmake lint\n```\n")
    result = run_verify(repo_root=root, readme_paths=["OTHER.md"])
    assert result.passed and len(result.results) == 1


def test_run_verify_scans_nested_readmes(tmp_path):
    """Per-package READMEs are scanned too."""
    root = _repo(tmp_path, "no commands\n")
    (root / "pkg").mkdir()
    (root / "pkg" / "README.md").write_text("```bash\nmake docs\n```\n")
    assert run_verify(repo_root=root).failed


def test_run_verify_without_readme_has_no_results(tmp_path):
    """A repo with no README has nothing to verify."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    result = run_verify(repo_root=tmp_path)
    assert result.results == [] and result.passed


# --- resolve_readmes ---------------------------------------------------------


def test_resolve_readmes_discovers_by_default(tmp_path):
    """Without an explicit list, READMEs are discovered recursively."""
    (tmp_path / "README.md").write_text("x")
    assert resolve_readmes(tmp_path) == [tmp_path / "README.md"]


def test_resolve_readmes_drops_missing_explicit_paths(tmp_path):
    """Explicit paths that do not exist are dropped."""
    (tmp_path / "README.md").write_text("x")
    found = resolve_readmes(tmp_path, ["README.md", "GONE.md"])
    assert found == [tmp_path / "README.md"]


def test_resolve_readmes_honours_exclude_dirs(tmp_path):
    """Extra excluded directories are skipped during discovery."""
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "README.md").write_text("x")
    assert resolve_readmes(tmp_path, None, ["vendor"]) == []


def test_resolve_readmes_accepts_absolute_paths(tmp_path):
    """Absolute explicit paths are used as given."""
    path = tmp_path / "README.md"
    path.write_text("x")
    assert resolve_readmes(tmp_path, [str(path)]) == [path]


# --- result model ------------------------------------------------------------


def test_verify_result_only_broken_fails():
    """Unverifiable and verified results do not fail the run."""
    ok = VerifyResult(
        results=[_result(ClaimStatus.VERIFIED), _result(ClaimStatus.UNVERIFIABLE)]
    )
    bad = VerifyResult(results=[_result(ClaimStatus.BROKEN)])
    assert ok.passed and not ok.failed
    assert bad.failed and not bad.passed


# --- report ------------------------------------------------------------------


def test_report_no_commands():
    """An empty result says no commands were found."""
    assert "no shell commands" in format_verify_report(VerifyResult())


def test_report_passing_counts_checks():
    """A passing report states how many checks were verified."""
    text = format_verify_report(
        VerifyResult(
            results=[_result(ClaimStatus.VERIFIED), _result(ClaimStatus.UNVERIFIABLE)]
        )
    )
    assert "✅" in text and "1 README command check(s) verified" in text
    assert "1 unverifiable" in text


def test_report_failing_lists_broken_with_location_and_advice():
    """A failing report shows the command, location, reason and the ignore hint."""
    text = format_verify_report(
        VerifyResult(
            results=[_result(ClaimStatus.BROKEN, "make docs", "target missing")]
        )
    )
    assert "❌" in text
    assert "`make docs`" in text
    assert "README.md line 3: target missing" in text
    assert "verified: 0 · broken: 1 · unverifiable: 0" in text
    assert "readme-drift: ignore" in text


def test_report_verbose_lists_every_check():
    """Verbose mode lists verified and unverifiable checks too."""
    text = format_verify_report(
        VerifyResult(
            results=[
                _result(ClaimStatus.VERIFIED, "make lint", "ok"),
                _result(ClaimStatus.UNVERIFIABLE, "pip install x", "no verifier"),
            ]
        ),
        verbose=True,
    )
    assert "[verified] `make lint`" in text
    assert "[unverifiable] `pip install x`" in text


# --- CLI ---------------------------------------------------------------------


def _invoke(args, verify_result):
    """Invoke the CLI with the diff check passing and verify mocked."""
    from unittest.mock import MagicMock, patch

    with (
        patch("readme_drift.cli.run_check", return_value=MagicMock(passed=True)),
        patch("readme_drift.cli.format_report", return_value=""),
        patch("readme_drift.cli.run_verify", return_value=verify_result) as rv,
    ):
        result = CliRunner().invoke(main, args)
    return result, rv


def test_cli_verify_failure_exits_nonzero():
    """--verify with a broken claim fails the run."""
    result, _ = _invoke(
        ["--verify"], VerifyResult(results=[_result(ClaimStatus.BROKEN)])
    )
    assert result.exit_code == 1
    assert "verify" in result.output


def test_cli_verify_failure_is_softened_by_warn_only():
    """--warn-only keeps a broken claim from failing the run."""
    result, _ = _invoke(
        ["--verify", "--warn-only"],
        VerifyResult(results=[_result(ClaimStatus.BROKEN)]),
    )
    assert result.exit_code == 0


def test_cli_verify_pass_exits_zero():
    """--verify with only verified claims passes."""
    result, _ = _invoke(
        ["--verify"], VerifyResult(results=[_result(ClaimStatus.VERIFIED)])
    )
    assert result.exit_code == 0


def test_cli_without_verify_does_not_run_verification():
    """Verification is opt-in."""
    result, rv = _invoke([], VerifyResult())
    assert result.exit_code == 0
    rv.assert_not_called()


def test_cli_verify_forwards_readme_options():
    """README targeting options reach run_verify."""
    _, rv = _invoke(
        ["--verify", "--readme-paths", "A.md", "--readme-exclude-dirs", "v"],
        VerifyResult(),
    )
    kwargs = rv.call_args.kwargs
    assert kwargs["readme_paths"] == ["A.md"]
    assert kwargs["readme_exclude_dirs"] == ["v"]
