"""CLI entry point for readme-drift."""

import sys
import tomllib
from pathlib import Path
from typing import Any

import click

from . import messages
from .constants import DEFAULT_NOISE_BLOCKLIST, README_TEMPLATE
from .drift_checker import run_check
from .git import get_repo_root, validate_repo_root
from .report import format_report
from .tips import first_use_tip, tips_disabled


def _load_toml_config(repo_root: Path | None) -> dict:
    """Read [tool.readme-drift] from pyproject.toml nearest to cwd or repo_root."""
    search_dirs = [repo_root] if repo_root else []
    search_dirs.append(Path.cwd())
    for directory in search_dirs:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            try:
                with candidate.open("rb") as f:
                    data = tomllib.load(f)
                return data.get("tool", {}).get("readme-drift", {})
            except Exception:
                return {}
    return {}


def validate_options(
    *,
    readme_paths: tuple[str, ...],
    readme_exclude_dirs: tuple[str, ...],
    plain_text_search: bool,
    noise_blocklist: tuple[str, ...],
    noise_allowlist: tuple[str, ...],
) -> list[str]:
    """Return warnings for option combinations where one flag overrides another.

    Parameters
    ----------
    readme_paths : tuple[str, ...]
        Explicit README paths.
    readme_exclude_dirs : tuple[str, ...]
        Extra directory names to skip during README discovery.
    plain_text_search : bool
        Whether plain-text matching is enabled.
    noise_blocklist : tuple[str, ...]
        Replacement noise blocklist words.
    noise_allowlist : tuple[str, ...]
        Words to remove from the built-in noise blocklist.

    Returns
    -------
    list[str]
        One warning message per conflicting combination; empty if none.
    """
    warnings: list[str] = []
    if readme_paths and readme_exclude_dirs:
        warnings.append(messages.WARN_READMEPATHS_EXCLUDEDIRS)
    if not plain_text_search and (noise_blocklist or noise_allowlist):
        warnings.append(messages.WARN_NO_PLAIN_TEXT_NOISE)
    if noise_blocklist and noise_allowlist:
        warnings.append(messages.WARN_BLOCKLIST_OVERRIDES_ALLOWLIST)
    return warnings


class _ConfigCommand(click.Command):
    """Click command that loads pyproject defaults before parsing arguments."""

    def make_context(
        self, info_name: str | None, args: list[str], **extra: Any
    ) -> click.Context:
        """Create the click context with ``[tool.readme-drift]`` values as defaults.

        Parameters
        ----------
        info_name : str or None
            Name of the command as invoked.
        args : list[str]
            Raw command-line arguments; ``--repo-root`` is pre-scanned here.
        **extra : Any
            Extra keyword arguments forwarded to ``click.Command.make_context``.

        Returns
        -------
        click.Context
            Context whose ``meta["toml_cfg"]`` holds the loaded config section.
        """
        repo_root: Path | None = None
        for i, arg in enumerate(args):
            if arg == "--repo-root" and i + 1 < len(args):
                repo_root = Path(args[i + 1])
                break
        cfg = _load_toml_config(repo_root)
        if cfg:
            # Click default_map keys use Python param names (underscores).
            extra.setdefault("default_map", {}).update(
                {k.replace("-", "_"): v for k, v in cfg.items()}
            )
        ctx = super().make_context(info_name, args, **extra)
        ctx.meta["toml_cfg"] = cfg
        return ctx


@click.command(
    cls=_ConfigCommand,
    context_settings={"help_option_names": ["-h", "--help"]},
)
# -- Scaffolding --------------------------------------------------------------
@click.option(
    "--init",
    is_flag=True,
    default=False,
    help=(
        "Create a README.md with bare template subheadings and exit. "
        "Refuses to overwrite an existing, non-empty README."
    ),
)
# -- Git source --------------------------------------------------------------
@click.option(
    "--base-ref",
    default="HEAD",
    show_default=True,
    help="Git ref to diff against.",
)
@click.option(
    "--staged",
    is_flag=True,
    default=False,
    help="Check staged changes only. Used by the pre-commit hook.",
)
@click.option(
    "--repo-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Repository root (auto-detected if not set).",
)
# -- Source filtering --------------------------------------------------------
@click.option(
    "--exclude",
    multiple=True,
    metavar="PATTERN",
    help="Glob pattern for source files/dirs to skip (repeatable).",
)
@click.option(
    "--include-private",
    is_flag=True,
    default=False,
    help="Track private (underscore-prefixed) Python symbols.",
)
# -- README targeting --------------------------------------------------------
@click.option(
    "--readme-paths",
    multiple=True,
    metavar="PATH",
    help=(
        "Explicit README file to scan (repeatable). "
        "When set, disables recursive README discovery. "
        "Incompatible with --readme-exclude-dirs."
    ),
)
@click.option(
    "--readme-exclude-dirs",
    multiple=True,
    metavar="DIR",
    help=(
        "Extra directory name to skip during README discovery (repeatable). "
        "Ignored when --readme-paths is set."
    ),
)
# -- Symbol filtering --------------------------------------------------------
@click.option(
    "--symbol-allowlist",
    multiple=True,
    metavar="SYMBOL",
    help=(
        "Always flag this symbol when changed, even if not in the README (repeatable). "
        "Use for critical public API symbols."
    ),
)
@click.option(
    "--symbol-denylist",
    multiple=True,
    metavar="SYMBOL",
    help=(
        "Never flag this symbol, even if changed and found in the README (repeatable). "
        "Takes priority over --symbol-allowlist."
    ),
)
@click.option(
    "--min-symbol-length",
    default=4,
    show_default=True,
    metavar="N",
    help=(
        "Minimum symbol length for plain-text matching. "
        "Shorter symbols are still matched inside backtick spans."
    ),
)
@click.option(
    "--noise-blocklist",
    multiple=True,
    default=(),
    metavar="WORD",
    help=(
        "Replace the built-in noise blocklist with these words (repeatable). "
        "To disable noise suppression entirely, set ``noise-blocklist = []`` "
        "in pyproject.toml. Ignored when --noise-allowlist is sufficient."
    ),
)
@click.option(
    "--noise-allowlist",
    multiple=True,
    default=(),
    metavar="WORD",
    help=(
        "Remove specific words from the built-in noise blocklist (repeatable). "
        "Use this to re-enable plain-text matching for a single word without "
        "replacing the entire blocklist. Ignored when --noise-blocklist is set."
    ),
)
# -- Output ------------------------------------------------------------------
@click.option(
    "--plain-text-search/--no-plain-text-search",
    default=True,
    help="Match symbols as plain text in addition to backtick spans. Default: enabled.",
)
@click.option(
    "--warn-only",
    is_flag=True,
    default=False,
    help="Print findings but always exit 0.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print per-symbol scan outcomes after the main report.",
)
@click.pass_context
def main(
    ctx: click.Context,
    init: bool,
    base_ref: str,
    staged: bool,
    repo_root: Path | None,
    exclude: tuple[str, ...],
    include_private: bool,
    readme_paths: tuple[str, ...],
    readme_exclude_dirs: tuple[str, ...],
    symbol_allowlist: tuple[str, ...],
    symbol_denylist: tuple[str, ...],
    min_symbol_length: int,
    noise_blocklist: tuple[str, ...],
    noise_allowlist: tuple[str, ...],
    plain_text_search: bool,
    warn_only: bool,
    verbose: bool,
) -> None:
    """Check if README may be stale after code changes.

    \f

    Parameters
    ----------
    ctx : click.Context
        Click context carrying the loaded ``pyproject.toml`` config.
    init : bool
        Create a README template and exit.
    base_ref : str
        Git ref to diff against.
    staged : bool
        Check staged changes only.
    repo_root : Path or None
        Repository root; auto-detected if None.
    exclude : tuple[str, ...]
        Glob patterns for source files or directories to skip.
    include_private : bool
        Track private (underscore-prefixed) Python symbols.
    readme_paths : tuple[str, ...]
        Explicit README files; disables discovery.
    readme_exclude_dirs : tuple[str, ...]
        Extra directory names to skip during README discovery.
    symbol_allowlist : tuple[str, ...]
        Symbols always flagged when changed.
    symbol_denylist : tuple[str, ...]
        Symbols never flagged; takes priority over the allowlist.
    min_symbol_length : int
        Minimum symbol length for plain-text matching.
    noise_blocklist : tuple[str, ...]
        Words replacing the built-in noise blocklist.
    noise_allowlist : tuple[str, ...]
        Words removed from the built-in noise blocklist.
    plain_text_search : bool
        Match symbols as plain text as well as in backtick spans.
    warn_only : bool
        Print findings but always exit 0.
    verbose : bool
        Print per-symbol scan outcomes.
    """  # noqa: D301 -- the literal \f truncates click's --help text
    if init:
        root = (
            validate_repo_root(repo_root) if repo_root is not None else get_repo_root()
        )
        target = root / "README.md"
        if target.exists() and target.read_text(encoding="utf-8").strip():
            click.echo(messages.init_refused(target), err=True)
            sys.exit(1)
        target.write_text(README_TEMPLATE, encoding="utf-8")
        click.echo(messages.init_created(target))
        sys.exit(0)

    cfg: dict = ctx.meta.get("toml_cfg", {})

    for warning in validate_options(
        readme_paths=readme_paths,
        readme_exclude_dirs=readme_exclude_dirs,
        plain_text_search=plain_text_search,
        noise_blocklist=noise_blocklist,
        noise_allowlist=noise_allowlist,
    ):
        click.echo(warning, err=True)

    # -- Noise-blocklist resolution ------------------------------------------
    # Priority: CLI --noise-blocklist (full replace) > pyproject.toml noise-blocklist
    #           > DEFAULT_NOISE_BLOCKLIST minus noise-allowlist words.
    # None signals run_check to use the built-in default unchanged.
    # An empty list explicitly disables noise suppression.
    resolved_noise_blocklist: list[str] | None
    if noise_blocklist:
        # Full replacement — ignore noise_allowlist (warned above).
        resolved_noise_blocklist = list(noise_blocklist)
    elif "noise-blocklist" in cfg:
        # TOML replacement — noise_allowlist not applied to custom lists.
        resolved_noise_blocklist = list(cfg["noise-blocklist"])
    else:
        # Use built-in default, subtract any allowlisted words.
        _allowlist: set[str] = set(noise_allowlist)
        if "noise-allowlist" in cfg:
            _allowlist.update(cfg.get("noise-allowlist", []))
        if _allowlist:
            resolved_noise_blocklist = [
                w for w in DEFAULT_NOISE_BLOCKLIST if w not in _allowlist
            ]
        else:
            resolved_noise_blocklist = None

    result = run_check(
        base_ref=base_ref,
        repo_root=repo_root,
        staged=staged,
        include_private=include_private,
        plain_text=plain_text_search,
        exclude=list(exclude),
        symbol_allowlist=list(symbol_allowlist) or None,
        symbol_denylist=list(symbol_denylist) or None,
        readme_paths=list(readme_paths) or None,
        readme_exclude_dirs=list(readme_exclude_dirs) or None,
        min_symbol_length=min_symbol_length,
        noise_blocklist=resolved_noise_blocklist,
        verbose=verbose,
    )

    click.echo(format_report(result))

    if not tips_disabled(cfg):
        root = (
            validate_repo_root(repo_root) if repo_root is not None else get_repo_root()
        )
        tip = first_use_tip(root, passed=result.passed, cfg=cfg)
        if tip:
            click.echo(tip, err=True)

    sys.exit(0 if (result.passed or warn_only) else 1)


if __name__ == "__main__":
    main()
