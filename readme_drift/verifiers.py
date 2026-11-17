"""Verify README shell-command claims against names the repository owns."""

import ast
import fnmatch
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from . import messages
from .config_diff import MakefileExtractor
from .models import Claim, ClaimResult, ClaimStatus

_V = ClaimStatus.VERIFIED
_B = ClaimStatus.BROKEN
_U = ClaimStatus.UNVERIFIABLE

_Check = tuple[ClaimStatus, str]
_Verifier = Callable[[Claim, "RepoFacts"], list[_Check]]

_MAKEFILE_NAMES = ("GNUmakefile", "makefile", "Makefile")
_COMPOSE_NAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)
_MAKE_RULE_RE = re.compile(r"^([^\s#:=][^#:=]*):(?!=)")
_MAKE_SPECIAL = frozenset(
    {".PHONY", ".DEFAULT", ".SUFFIXES", ".PRECIOUS", ".SILENT", ".ONESHELL"}
)
_MAKE_VALUE_OPTS = frozenset(
    {"-l", "--load-average", "-o", "--old-file", "-W", "--what-if", "-I"}
)
_MAKE_ALT_OPTS = frozenset({"-C", "--directory", "-f", "--file", "--makefile"})
_GENERATED_DIRS = frozenset(
    {
        "build",
        "dist",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "target",
        "out",
        "obj",
        ".tox",
        "site",
        "htmlcov",
        "__pycache__",
    }
)
_JS_ALT_OPTS = frozenset(
    {"--prefix", "-C", "--cwd", "--workspace", "-w", "--workspaces", "--filter"}
)
_NPM_RUN = frozenset({"run", "run-script", "rum", "urn"})
_COMPOSE_GLOBAL_VALUE_OPTS = frozenset(
    {
        "-f",
        "--file",
        "-p",
        "--project-name",
        "--profile",
        "--env-file",
        "--project-directory",
        "--ansi",
        "--parallel",
        "--progress",
    }
)
_COMPOSE_VALUE_OPTS = frozenset(
    {
        "--scale",
        "-t",
        "--timeout",
        "-e",
        "--env",
        "-u",
        "--user",
        "-w",
        "--workdir",
        "--name",
        "--entrypoint",
        "-v",
        "--volume",
        "-p",
        "--publish",
        "--pull",
        "--index",
        "-l",
        "--label",
        "--exit-code-from",
        "--attach",
        "--no-attach",
        "--since",
        "--until",
        "-n",
        "--tail",
        "--cap-add",
        "--cap-drop",
        "--build-arg",
    }
)
_COMPOSE_SERVICE_COMMANDS = frozenset(
    {
        "up",
        "run",
        "start",
        "stop",
        "restart",
        "build",
        "logs",
        "exec",
        "pull",
        "push",
        "rm",
        "kill",
        "pause",
        "unpause",
        "create",
        "top",
        "port",
    }
)
_COMPOSE_SINGLE_SERVICE = frozenset({"run", "exec"})
# Heads whose file-valued option is checked, with the subcommands that apply
# (None = any). ``docker compose`` is handled by its own verifier because
# ``-f`` there means "follow" after the subcommand.
_FILE_ARG_RULES: dict[str, tuple[frozenset[str] | None, frozenset[str]]] = {
    "make": (None, frozenset({"-f", "--file", "--makefile"})),
    "docker": (frozenset({"build", "buildx"}), frozenset({"-f", "--file"})),
    "kubectl": (
        frozenset({"apply", "create", "delete", "replace", "diff"}),
        frozenset({"-f", "--filename"}),
    ),
    "helm": (None, frozenset({"-f", "--values"})),
}
_OPTION_NAME_CALLS = frozenset({"option", "add_argument", "Option", "Argument"})
_ALWAYS_OK_FLAGS = frozenset({"--help", "-h", "--version"})
_PYTHON_RE = re.compile(r"^python[0-9.]*$")
_SHELL_HEADS = frozenset({"bash", "sh", "zsh", "source", "."})


@dataclass
class _MakeFacts:
    """Targets, patterns and uncertainty read from the repository's Makefile."""

    targets: set[str]
    patterns: set[str]
    uncertain: bool
    filename: str


class RepoFacts:
    """Lazily read, cached facts about names the repository defines."""

    def __init__(self, root: Path) -> None:
        """Remember the repository root; nothing is read until requested."""
        self.root = root
        self._cache: dict[str, object] = {}

    def _cached(self, key: str, loader: Callable[[], object]) -> object:
        """Return a cached value, computing it with ``loader`` on first use."""
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]

    def bases_for(self, readme_path: Path) -> list["RepoFacts"]:
        """Return the facts to consult for a README: its own directory, then the root.

        Parameters
        ----------
        readme_path : Path
            README the command was found in.

        Returns
        -------
        list[RepoFacts]
            Facts for the README's directory (when it is a different directory
            inside the repository) followed by the repository root facts.
        """
        root = self.root.resolve()
        directory = readme_path.resolve().parent
        if directory == root or not directory.is_relative_to(root):
            return [self]
        local = self._cached(f"dir:{directory}", lambda: RepoFacts(directory))
        return [local, self]  # type: ignore[list-item]

    def make_facts(self) -> _MakeFacts | None:
        """Return the Makefile's targets, or None if there is no Makefile.

        Returns
        -------
        _MakeFacts or None
            Targets, ``%`` patterns, whether some targets may be hidden behind
            includes or variables, and the Makefile name.
        """
        return self._cached("make", self._load_make)

    def _load_make(self) -> _MakeFacts | None:
        """Parse the first Makefile found in the repository root."""
        for name in _MAKEFILE_NAMES:
            path = self.root / name
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                return _parse_makefile(text, name)
        return None

    def npm_scripts(self) -> set[str] | None:
        """Return the script names in ``package.json``, or None if unavailable.

        Returns
        -------
        set[str] or None
            Script names, or None if there is no readable ``package.json``.
        """
        return self._cached("npm", self._load_npm)

    def _load_npm(self) -> set[str] | None:
        """Read script names from the root ``package.json``."""
        path = self.root / "package.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        scripts = data.get("scripts") if isinstance(data, dict) else None
        return set(scripts) if isinstance(scripts, dict) else set()

    def compose_services(
        self, files: list[Path] | None = None
    ) -> tuple[set[str], bool, str] | None:
        """Return compose service names, or None if no compose file is readable.

        Parameters
        ----------
        files : list[Path] or None, optional
            Compose files to read; defaults to the standard names in the
            repository root.

        Returns
        -------
        tuple[set[str], bool, str] or None
            Service names, whether an ``include`` may hide more services, and
            the file names read.
        """
        candidates = files or [self.root / n for n in _COMPOSE_NAMES]
        services: set[str] = set()
        uncertain = False
        names: list[str] = []
        for path in candidates:
            if not path.is_file():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            names.append(path.name)
            found = data.get("services")
            if isinstance(found, dict):
                services.update(str(k) for k in found)
            if "include" in data:
                uncertain = True
        if not names:
            return None
        return services, uncertain, ", ".join(names)

    def cli_flags(self, head: str) -> set[str] | None:
        """Return the long options a project console script defines, if known.

        Parameters
        ----------
        head : str
            Command name, matched against ``[tool.poetry.scripts]`` and
            ``[project.scripts]`` in ``pyproject.toml``.

        Returns
        -------
        set[str] or None
            Option names read statically from the entry point's module, or
            None if ``head`` is not a project script or its options cannot be
            read statically.
        """
        entry = self.entry_points().get(head)
        if entry is None:
            return None
        return self._cached(f"flags:{head}", lambda: self._load_flags(entry))

    def entry_points(self) -> dict[str, str]:
        """Return the project's console scripts as name to ``module:func``.

        Returns
        -------
        dict[str, str]
            Console script names mapped to their entry-point targets.
        """
        return self._cached("entry", self._load_entry_points)

    def _load_entry_points(self) -> dict[str, str]:
        """Read console scripts from ``pyproject.toml``."""
        path = self.root / "pyproject.toml"
        if not path.is_file():
            return {}
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            return {}
        scripts: dict[str, str] = {}
        scripts.update(data.get("project", {}).get("scripts", {}))
        scripts.update(data.get("tool", {}).get("poetry", {}).get("scripts", {}))
        return {str(k): str(v) for k, v in scripts.items()}

    def _load_flags(self, entry: str) -> set[str] | None:
        """Statically read option names from an entry point's module."""
        module = entry.split(":", 1)[0]
        parts = module.split(".")
        for base in (self.root, self.root / "src"):
            for candidate in (
                base.joinpath(*parts).with_suffix(".py"),
                base.joinpath(*parts, "__init__.py"),
            ):
                if candidate.is_file():
                    return _static_flags(candidate.read_text(encoding="utf-8"))
        return None


def _parse_makefile(text: str, filename: str) -> _MakeFacts:
    """Collect targets and uncertainty markers from Makefile text."""
    extracted = set(MakefileExtractor().extract(text))
    targets = {name for name in extracted if "%" not in name}
    patterns = {name for name in extracted if "%" in name}
    uncertain = False
    for line in text.splitlines():
        if not line.strip() or line.startswith(("\t", " ", "#")):
            continue
        if re.match(r"^-?include\s", line):
            uncertain = True
            continue
        match = _MAKE_RULE_RE.match(line)
        if not match:
            continue
        for name in match.group(1).split():
            if name in _MAKE_SPECIAL:
                continue
            if "$(" in name or "${" in name:
                uncertain = True
            elif "%" in name:
                patterns.add(name)
            else:
                targets.add(name)
    return _MakeFacts(targets, patterns, uncertain, filename)


def _static_flags(source: str) -> set[str] | None:
    """Return option names declared via click/argparse-style calls, or None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name not in _OPTION_NAME_CALLS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                for part in arg.value.split("/"):
                    if part.startswith("-"):
                        flags.add(part.strip())
    return flags | _ALWAYS_OK_FLAGS if flags else None


def _check_path(root: Path, value: str) -> _Check | None:
    """Check that a repo-relative path exists; None if it cannot be judged."""
    if value == "-" or any(c in value for c in "$*?<>{}") or "://" in value:
        return None
    if value.startswith(("~", "/")):
        return _U, messages.REASON_PATH_OUTSIDE.format(path=value)
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        return _U, messages.REASON_PATH_OUTSIDE.format(path=value)
    if target.exists():
        return _V, messages.REASON_PATH_OK.format(path=value)
    first = Path(value).parts[0] if Path(value).parts else ""
    if first in _GENERATED_DIRS:
        return _U, messages.REASON_PATH_GENERATED.format(path=value)
    return _B, messages.REASON_PATH_MISSING.format(path=value)


def _option_values(args: tuple[str, ...], names: frozenset[str]) -> list[str]:
    """Return the values given to any of the named options."""
    values: list[str] = []
    for i, arg in enumerate(args):
        if arg in names and i + 1 < len(args):
            values.append(args[i + 1])
        else:
            for name in names:
                if name.startswith("--") and arg.startswith(name + "="):
                    values.append(arg.split("=", 1)[1])
    return values


def _first_positional(args: tuple[str, ...], value_opts: frozenset[str]) -> str | None:
    """Return the first non-option argument, skipping option values."""
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in value_opts:
            skip = True
        elif not arg.startswith("-"):
            return arg
    return None


def _file_arg_checks(claim: Claim, root: Path) -> list[_Check]:
    """Check files passed to options such as ``make -f`` or ``kubectl apply -f``."""
    rule = _FILE_ARG_RULES.get(claim.head)
    if rule is None:
        return []
    subcommands, options = rule
    if subcommands is not None and (not claim.args or claim.args[0] not in subcommands):
        return []
    checks: list[_Check] = []
    for value in _option_values(claim.args, options):
        result = _check_path(root, value)
        if result is not None:
            checks.append(result)
    return checks


def _make_target_args(args: tuple[str, ...]) -> list[str]:
    """Return the make targets named in an argument list."""
    targets: list[str] = []
    skip = False
    for i, arg in enumerate(args):
        if skip:
            skip = False
        elif arg in {"-j", "--jobs"}:
            skip = i + 1 < len(args) and args[i + 1].isdigit()
        elif arg in _MAKE_VALUE_OPTS:
            skip = True
        elif arg.startswith("-") or "=" in arg:
            continue
        else:
            targets.append(arg)
    return targets


def _verify_make(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify ``make <target>`` against the Makefile's targets."""
    if any(
        a in _MAKE_ALT_OPTS or a.startswith(("--directory=", "--file=", "--makefile="))
        for a in claim.args
    ):
        return [(_U, messages.REASON_MAKE_ALT)]
    data = facts.make_facts()
    if data is None:
        return [(_U, messages.REASON_MAKE_NO_FILE)]
    checks: list[_Check] = []
    for name in _make_target_args(claim.args):
        if name in data.targets or any(
            fnmatch.fnmatchcase(name, p.replace("%", "*")) for p in data.patterns
        ):
            checks.append(
                (_V, messages.REASON_MAKE_OK.format(name=name, file=data.filename))
            )
        elif data.uncertain:
            checks.append(
                (
                    _U,
                    messages.REASON_MAKE_UNCERTAIN.format(
                        name=name, file=data.filename
                    ),
                )
            )
        else:
            checks.append(
                (_B, messages.REASON_MAKE_MISSING.format(name=name, file=data.filename))
            )
    return checks


def _verify_js(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify ``npm run`` / ``pnpm run`` / ``yarn`` scripts against package.json."""
    args = claim.args
    if "--" in args:
        args = args[: args.index("--")]
    if any(a in _JS_ALT_OPTS or a.startswith(("--prefix=", "--cwd=")) for a in args):
        return [(_U, messages.REASON_JS_ALT)]
    scripts = facts.npm_scripts()
    if scripts is None:
        return [(_U, messages.REASON_JS_NO_FILE)]
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return [(_U, messages.REASON_JS_NOT_SCRIPT)]
    explicit_run = False
    if claim.head == "yarn":
        if positionals[0] == "run":
            explicit_run = True
            name = positionals[1] if len(positionals) > 1 else None
        else:
            name = positionals[0]
    elif positionals[0] in _NPM_RUN:
        explicit_run = True
        name = positionals[1] if len(positionals) > 1 else None
    else:
        return [(_U, messages.REASON_JS_NOT_SCRIPT)]
    if name is None:
        return [(_U, messages.REASON_JS_NOT_SCRIPT)]
    if name in scripts:
        return [(_V, messages.REASON_JS_OK.format(name=name))]
    if explicit_run:
        return [(_B, messages.REASON_JS_MISSING.format(name=name))]
    return [(_U, messages.REASON_JS_MAYBE.format(name=name, tool=claim.head))]


def _compose_args(claim: Claim) -> tuple[str, ...] | None:
    """Return the arguments after ``compose``, or None if not a compose command."""
    if claim.head == "docker-compose":
        return claim.args
    if claim.head == "docker" and claim.args[:1] == ("compose",):
        return claim.args[1:]
    return None


def _verify_compose(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify ``docker compose`` file arguments and service names."""
    args = _compose_args(claim)
    if args is None:
        return [(_U, messages.REASON_COMPOSE_NOT_COMPOSE)]
    # Global options come before the subcommand.
    files: list[str] = []
    subcommand_index = None
    skip = False
    for i, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg in {"-f", "--file"} and i + 1 < len(args):
            files.append(args[i + 1])
            skip = True
        elif arg.startswith("--file="):
            files.append(arg.split("=", 1)[1])
        elif arg in _COMPOSE_GLOBAL_VALUE_OPTS:
            skip = True
        elif not arg.startswith("-"):
            subcommand_index = i
            break
    checks: list[_Check] = []
    paths: list[Path] = []
    for value in files:
        result = _check_path(facts.root, value)
        if result is not None:
            checks.append(result)
        paths.append(facts.root / value)
    if subcommand_index is None:
        return checks
    subcommand = args[subcommand_index]
    if subcommand not in _COMPOSE_SERVICE_COMMANDS:
        checks.append((_U, messages.REASON_COMPOSE_NO_SERVICES.format(sub=subcommand)))
        return checks
    data = facts.compose_services(paths or None)
    if data is None:
        checks.append((_U, messages.REASON_COMPOSE_NO_FILE))
        return checks
    services, uncertain, filenames = data
    names = _compose_service_args(
        args[subcommand_index + 1 :], single=subcommand in _COMPOSE_SINGLE_SERVICE
    )
    for name in names:
        if name in services:
            checks.append(
                (
                    _V,
                    messages.REASON_COMPOSE_OK.format(name=name, file=filenames),
                )
            )
        elif uncertain:
            checks.append((_U, messages.REASON_COMPOSE_UNCERTAIN.format(name=name)))
        else:
            checks.append(
                (
                    _B,
                    messages.REASON_COMPOSE_MISSING.format(name=name, file=filenames),
                )
            )
    return checks


def _compose_service_args(args: tuple[str, ...], *, single: bool) -> list[str]:
    """Return the service names in a compose subcommand's arguments."""
    names: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in _COMPOSE_VALUE_OPTS:
            skip = True
        elif arg.startswith("-"):
            continue
        else:
            names.append(arg)
            if single:
                break
    return names


def _verify_own_cli(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify long options of the project's own console script."""
    flags = facts.cli_flags(claim.head)
    if flags is None:
        return [(_U, messages.REASON_CLI_UNREADABLE.format(head=claim.head))]
    checks: list[_Check] = []
    for arg in claim.args:
        if arg == "--":
            break
        if not arg.startswith("--"):
            continue
        flag = arg.split("=", 1)[0]
        if flag in flags:
            checks.append(
                (_V, messages.REASON_CLI_OK.format(head=claim.head, flag=flag))
            )
        else:
            checks.append(
                (_B, messages.REASON_CLI_MISSING.format(head=claim.head, flag=flag))
            )
    return checks


def _module_check(root: Path, module: str) -> _Check:
    """Check a ``python -m`` module against the repository layout."""
    parts = module.split(".")
    for base in (root, root / "src"):
        top_exists = (base / parts[0]).is_dir() or (base / f"{parts[0]}.py").is_file()
        if not top_exists:
            continue
        target = base.joinpath(*parts)
        if target.is_dir() or target.with_suffix(".py").is_file():
            return _V, messages.REASON_PY_MODULE_OK.format(module=module)
        return _B, messages.REASON_PY_MODULE_MISSING.format(module=module)
    return _U, messages.REASON_PY_MODULE_EXTERNAL.format(module=module)


def _verify_python(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify the script or module a ``python`` command runs."""
    args = claim.args
    for i, arg in enumerate(args):
        if arg == "-c":
            return [(_U, messages.REASON_PY_INLINE)]
        if arg == "-m" and i + 1 < len(args):
            return [_module_check(facts.root, args[i + 1])]
    script = _first_positional(args, frozenset({"-W", "-X", "-Q"}))
    if script is None:
        return []
    result = _check_path(facts.root, script)
    return [result] if result is not None else []


def _verify_shell(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Verify the script a ``bash`` / ``sh`` / ``source`` command runs."""
    if "-c" in claim.args:
        return [(_U, messages.REASON_PY_INLINE)]
    script = _first_positional(claim.args, frozenset())
    if script is None:
        return []
    result = _check_path(facts.root, script)
    return [result] if result is not None else []


_VERIFIERS: dict[str, _Verifier] = {
    "make": _verify_make,
    "npm": _verify_js,
    "pnpm": _verify_js,
    "yarn": _verify_js,
    "docker": _verify_compose,
    "docker-compose": _verify_compose,
    **{head: _verify_shell for head in _SHELL_HEADS},
}


def _verifier_for(head: str, facts: RepoFacts) -> _Verifier | None:
    """Return the verifier registered for a command head, if any."""
    if head in facts.entry_points():
        return _verify_own_cli
    if _PYTHON_RE.match(head):
        return _verify_python
    return _VERIFIERS.get(head)


_ABSENT_REASONS = frozenset(
    {
        messages.REASON_MAKE_NO_FILE,
        messages.REASON_JS_NO_FILE,
        messages.REASON_COMPOSE_NO_FILE,
    }
)


def _claim_checks(claim: Claim, facts: RepoFacts) -> list[_Check]:
    """Run every applicable check for a claim against one set of repository facts."""
    if claim.cwd_changed:
        checks: list[_Check] = [(_U, messages.REASON_CWD_CHANGED)]
    elif claim.head.startswith(("./", "../")) or "/" in claim.head:
        path_check = _check_path(facts.root, claim.head)
        checks = [path_check] if path_check is not None else []
    else:
        checks = _file_arg_checks(claim, facts.root)
        verifier = _verifier_for(claim.head, facts)
        if verifier is None:
            checks.append((_U, messages.REASON_NO_VERIFIER.format(head=claim.head)))
        else:
            checks.extend(verifier(claim, facts))
    return checks


def _has(checks: list[_Check], status: ClaimStatus) -> bool:
    """Return True if any check has the given status."""
    return any(s is status for s, _ in checks)


# Verified if either location verifies; broken only if every location where the
# thing could live lacks it; otherwise unverifiable.
def _merge_checks(per_base: list[list[_Check]]) -> list[_Check]:
    """Combine checks made next to the README and at the repo root into one outcome."""
    if len(per_base) == 1:
        return per_base[0]
    for checks in per_base:
        if _has(checks, _V) and not _has(checks, _B):
            return checks
    broken = [c for c in per_base if _has(c, _B)]
    if not broken:
        return next(
            (c for c in per_base if any(r not in _ABSENT_REASONS for _, r in c)),
            per_base[-1],
        )
    for checks in per_base:
        if checks not in broken and any(
            s is _U and r not in _ABSENT_REASONS for s, r in checks
        ):
            return checks
    return broken[-1]


def verify_claim(claim: Claim, facts: RepoFacts) -> list[ClaimResult]:
    """Verify one claim against repository-owned facts.

    Only names the repository defines are checked (Makefile targets,
    ``package.json`` scripts, compose services, paths, the project's own CLI
    options, local Python modules). Syntax of third-party tools is never
    judged, and anything uncertain is reported as unverifiable, not broken.

    Parameters
    ----------
    claim : Claim
        The command to verify.
    facts : RepoFacts
        Repository facts, shared across claims so each file is read once.

    Returns
    -------
    list[ClaimResult]
        One result per individual check; a single unverifiable result when
        nothing repo-owned could be checked.
    """
    per_base = [
        _claim_checks(claim, base) for base in facts.bases_for(claim.readme_path)
    ]
    checks = _merge_checks(per_base)
    if not checks:
        checks = [(_U, messages.REASON_NOTHING)]
    return [ClaimResult(claim, status, reason) for status, reason in checks]
