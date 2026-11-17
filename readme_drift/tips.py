"""One-time onboarding tips shown the first time readme-drift runs in a repo."""

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from .messages import BACKTICK_TIP

NO_TIPS_ENV = "README_DRIFT_NO_TIPS"

__all__ = ["BACKTICK_TIP", "NO_TIPS_ENV", "first_use_tip", "tips_disabled"]


def _marker_path(repo_root: Path, env: Mapping[str, str]) -> Path:
    cache_home = env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    digest = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(cache_home) / "readme-drift" / "tips" / f"backtick-{digest}"


def tips_disabled(
    cfg: Mapping[str, object], env: Mapping[str, str] | None = None
) -> bool:
    """True if tips are switched off via env var, CI, or ``tips = false``."""
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

    The tip is shown at most once per repository per machine. A marker file
    in the user cache directory records that it was shown.

    pre-commit hides the output of hooks that pass, so inside pre-commit a
    passing run neither shows nor consumes the tip; it appears on the first
    failing run, where the output is visible.

    If the marker cannot be written (read-only home, sandbox), the tip is
    skipped rather than repeated on every run.
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
