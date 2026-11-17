"""One-time onboarding tips shown the first time readme-drift runs in a repo."""

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from .messages import BACKTICK_TIP

NO_TIPS_ENV = "README_DRIFT_NO_TIPS"

__all__ = ["BACKTICK_TIP", "NO_TIPS_ENV", "first_use_tip", "tips_disabled"]


def _marker_path(repo_root: Path, env: Mapping[str, str]) -> Path:
    """Return the per-repo marker file recording that the tip was shown."""
    cache_home = env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    digest = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(cache_home) / "readme-drift" / "tips" / f"backtick-{digest}"


def tips_disabled(
    cfg: Mapping[str, object], env: Mapping[str, str] | None = None
) -> bool:
    """Return whether tips are switched off.

    Tips are off when ``README_DRIFT_NO_TIPS`` is set, when running in CI, or
    when ``tips = false`` is configured.

    Parameters
    ----------
    cfg : Mapping[str, object]
        The ``[tool.readme-drift]`` config section.
    env : Mapping[str, str] or None, optional
        Environment to inspect; defaults to ``os.environ``.

    Returns
    -------
    bool
        True if tips are disabled.
    """
    env = os.environ if env is None else env
    if env.get(NO_TIPS_ENV):
        return True
    if env.get("CI"):
        return True
    return cfg.get("tips", True) is False


def first_use_tip(
    repo_root: Path,
    *,
    passed: bool,
    cfg: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return the backtick tip if it should be shown now, else None.

    The tip is shown at most once per repository per machine, tracked by a
    marker file in the user cache directory. pre-commit hides the output of
    passing hooks, so inside pre-commit a passing run neither shows nor consumes
    the tip; it appears on the first failing run. If the marker cannot be
    written, the tip is skipped rather than repeated.

    Parameters
    ----------
    repo_root : Path
        Repository root, used to key the marker file.
    passed : bool
        Whether the check passed (or was skipped).
    cfg : Mapping[str, object] or None, optional
        The ``[tool.readme-drift]`` config section.
    env : Mapping[str, str] or None, optional
        Environment to inspect; defaults to ``os.environ``.

    Returns
    -------
    str or None
        The tip text, or None if it should not be shown.
    """
    _env = os.environ if env is None else env
    if tips_disabled(cfg or {}, _env):
        return None
    if passed and _env.get("PRE_COMMIT"):
        return None

    try:
        marker = _marker_path(repo_root, _env)
        if marker.exists():
            return None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        return None
    return BACKTICK_TIP
