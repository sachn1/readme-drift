"""Run claim verification across every README in a repository."""

from pathlib import Path

from .claims import extract_claims
from .drift_checker import resolve_readmes
from .git import get_repo_root, validate_repo_root
from .models import ClaimResult, VerifyResult
from .verifiers import RepoFacts, verify_claim


def run_verify(
    repo_root: Path | None = None,
    readme_paths: list[str] | None = None,
    readme_exclude_dirs: list[str] | None = None,
) -> VerifyResult:
    """Verify the shell commands in README code blocks against the repository.

    Unlike the diff-driven check, this scans every README in full, so it also
    catches commands that were already wrong before the current change.

    Parameters
    ----------
    repo_root : Path or None, optional
        Repository root; auto-detected if None.
    readme_paths : list[str] or None, optional
        Explicit README paths; disables discovery.
    readme_exclude_dirs : list[str] or None, optional
        Extra directory names to skip during README discovery.

    Returns
    -------
    VerifyResult
        One result per check, across all discovered READMEs.
    """
    root = validate_repo_root(repo_root) if repo_root is not None else get_repo_root()
    readmes = resolve_readmes(root, readme_paths, readme_exclude_dirs)
    facts = RepoFacts(root)
    results: list[ClaimResult] = []
    for readme in readmes:
        for claim in extract_claims(readme):
            results.extend(verify_claim(claim, facts))
    return VerifyResult(results=results, readme_paths=readmes)
