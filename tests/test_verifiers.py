"""Tests for verifying README command claims against repo-owned names."""

import json
from pathlib import Path

from readme_drift.models import Claim, ClaimStatus
from readme_drift.verifiers import RepoFacts, _static_flags, verify_claim

V = ClaimStatus.VERIFIED
B = ClaimStatus.BROKEN
U = ClaimStatus.UNVERIFIABLE


def _verify(root: Path, head: str, *args: str, cwd_changed: bool = False):
    """Verify a claim built from a head and arguments against a repo root."""
    claim = Claim(
        head=head,
        args=tuple(args),
        raw=" ".join([head, *args]),
        readme_path=root / "README.md",
        line_number=1,
        cwd_changed=cwd_changed,
    )
    return verify_claim(claim, RepoFacts(root))


def _statuses(results):
    """Return the status of each result."""
    return [r.status for r in results]


def _write(root: Path, name: str, text: str) -> None:
    """Write a file under the repo root, creating parent directories."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- generic -----------------------------------------------------------------


def test_unknown_head_is_unverifiable(tmp_path):
    """A command with no verifier is unverifiable, never broken."""
    assert _statuses(_verify(tmp_path, "pip", "install", "x")) == [U]


def test_cwd_change_makes_claim_unverifiable(tmp_path):
    """A claim after cd cannot be checked against the repo root."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "nope", cwd_changed=True)) == [U]


# --- make --------------------------------------------------------------------


def test_make_target_defined_is_verified(tmp_path):
    """A target defined in the Makefile is verified."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "lint")) == [V]


def test_make_missing_target_is_broken(tmp_path):
    """A target absent from the Makefile is broken."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    results = _verify(tmp_path, "make", "docs")
    assert _statuses(results) == [B]
    assert "docs" in results[0].reason


def test_make_multi_target_rule_line_is_understood(tmp_path):
    """Every name on a multi-target rule line counts as defined."""
    _write(tmp_path, "Makefile", "test lint: deps\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "lint", "test")) == [V, V]


def test_make_pattern_rule_matches_target(tmp_path):
    """A target matching a % pattern rule is verified."""
    _write(tmp_path, "Makefile", "%.o: %.c\n\tcc\n")
    assert _statuses(_verify(tmp_path, "make", "main.o")) == [V]


def test_make_include_makes_missing_target_unverifiable(tmp_path):
    """With an include, a missing target might live elsewhere."""
    _write(tmp_path, "Makefile", "include other.mk\nlint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "docs")) == [U]


def test_make_variable_target_makes_missing_unverifiable(tmp_path):
    """A rule whose target is a variable may define any name."""
    _write(tmp_path, "Makefile", "$(TARGETS):\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "docs")) == [U]


def test_make_skips_job_count_and_variable_assignments(tmp_path):
    """-j 4 and VAR=value are not targets."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "-j", "4", "CC=gcc", "lint")) == [V]


def test_make_dash_j_without_number_keeps_target(tmp_path):
    """make -j lint treats lint as a target."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "-j", "lint")) == [V]


def test_make_alternate_directory_is_unverifiable(tmp_path):
    """make -C dir targets another Makefile."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "-C", "sub", "nope")) == [U]


def test_make_without_makefile_is_unverifiable(tmp_path):
    """No Makefile means nothing to check against."""
    assert _statuses(_verify(tmp_path, "make", "lint")) == [U]


def test_make_f_file_is_path_checked(tmp_path):
    """make -f checks the named file exists."""
    results = _verify(tmp_path, "make", "-f", "build.mk", "all")
    assert B in _statuses(results)


def test_make_without_target_is_unverifiable(tmp_path):
    """A bare make has no target to verify."""
    _write(tmp_path, "Makefile", "lint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make")) == [U]


def test_make_variable_assignment_and_phony_do_not_define_targets(tmp_path):
    """Variable assignments and .PHONY are not targets."""
    _write(tmp_path, "Makefile", "CC := gcc\n.PHONY: lint\nlint:\n\techo\n")
    assert _statuses(_verify(tmp_path, "make", "CC", ".PHONY")) == [B, B]


# --- npm / yarn / pnpm -------------------------------------------------------


def _package(root: Path, scripts: dict[str, str]) -> None:
    """Write a package.json with the given scripts."""
    _write(root, "package.json", json.dumps({"scripts": scripts}))


def test_npm_run_existing_script_is_verified(tmp_path):
    """npm run of a defined script is verified."""
    _package(tmp_path, {"build": "tsc"})
    assert _statuses(_verify(tmp_path, "npm", "run", "build")) == [V]


def test_npm_run_missing_script_is_broken(tmp_path):
    """npm run of an undefined script is broken."""
    _package(tmp_path, {"build": "tsc"})
    assert _statuses(_verify(tmp_path, "npm", "run", "deploy")) == [B]


def test_npm_run_stops_at_double_dash(tmp_path):
    """Arguments after -- belong to the script, not npm."""
    _package(tmp_path, {"test": "jest"})
    assert _statuses(_verify(tmp_path, "npm", "run", "test", "--", "--watch")) == [V]


def test_pnpm_run_missing_script_is_broken(tmp_path):
    """pnpm run is checked like npm run."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "pnpm", "run", "x")) == [B]


def test_yarn_run_missing_script_is_broken(tmp_path):
    """yarn run of an undefined script is broken."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "yarn", "run", "x")) == [B]


def test_yarn_bare_missing_name_is_unverifiable(tmp_path):
    """yarn <name> may be a yarn command, so a miss is not broken."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "yarn", "dlx")) == [U]


def test_yarn_bare_existing_script_is_verified(tmp_path):
    """yarn <name> matching a script is verified."""
    _package(tmp_path, {"build": "x"})
    assert _statuses(_verify(tmp_path, "yarn", "build")) == [V]


def test_npm_install_is_not_a_script_invocation(tmp_path):
    """npm install is not judged against scripts."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "npm", "install")) == [U]


def test_npm_workspace_flag_is_unverifiable(tmp_path):
    """A workspace or prefix flag points at another package.json."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "npm", "--prefix", "web", "run", "x")) == [U]


def test_npm_without_package_json_is_unverifiable(tmp_path):
    """No package.json means nothing to check against."""
    assert _statuses(_verify(tmp_path, "npm", "run", "x")) == [U]


def test_npm_run_without_name_is_unverifiable(tmp_path):
    """npm run with no script name has nothing to verify."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "npm", "run")) == [U]


def test_npm_with_no_arguments_is_unverifiable(tmp_path):
    """A bare npm has nothing to verify."""
    _package(tmp_path, {})
    assert _statuses(_verify(tmp_path, "npm")) == [U]


def test_invalid_package_json_is_unverifiable(tmp_path):
    """Unreadable package.json is treated as absent."""
    _write(tmp_path, "package.json", "{not json")
    assert _statuses(_verify(tmp_path, "npm", "run", "x")) == [U]


# --- docker compose ----------------------------------------------------------

COMPOSE = "services:\n  web:\n    image: x\n  db:\n    image: y\n"


def test_compose_up_known_service_is_verified(tmp_path):
    """docker compose up of a defined service is verified."""
    _write(tmp_path, "docker-compose.yml", COMPOSE)
    assert _statuses(_verify(tmp_path, "docker", "compose", "up", "-d", "web")) == [V]


def test_compose_up_unknown_service_is_broken(tmp_path):
    """docker compose up of an undefined service is broken."""
    _write(tmp_path, "compose.yaml", COMPOSE)
    assert _statuses(_verify(tmp_path, "docker", "compose", "up", "cache")) == [B]


def test_docker_compose_v1_head_is_supported(tmp_path):
    """The docker-compose binary is checked the same way."""
    _write(tmp_path, "docker-compose.yml", COMPOSE)
    assert _statuses(_verify(tmp_path, "docker-compose", "up", "db")) == [V]


def test_compose_run_checks_only_first_positional(tmp_path):
    """compose run treats the first positional as the service, the rest as a command."""
    _write(tmp_path, "docker-compose.yml", COMPOSE)
    results = _verify(tmp_path, "docker", "compose", "run", "--rm", "web", "pytest")
    assert _statuses(results) == [V]


def test_compose_value_option_is_not_a_service(tmp_path):
    """--scale web=2 does not make 'web=2' a service name."""
    _write(tmp_path, "docker-compose.yml", COMPOSE)
    results = _verify(tmp_path, "docker", "compose", "up", "--scale", "web=2", "web")
    assert _statuses(results) == [V]


def test_compose_logs_follow_flag_is_not_a_file(tmp_path):
    """logs -f web means follow, not a compose file."""
    _write(tmp_path, "docker-compose.yml", COMPOSE)
    results = _verify(tmp_path, "docker", "compose", "logs", "-f", "web")
    assert _statuses(results) == [V]


def test_compose_file_option_reads_that_file(tmp_path):
    """-f selects the compose file whose services are checked."""
    _write(tmp_path, "ci/compose.yml", "services:\n  runner:\n    image: x\n")
    results = _verify(
        tmp_path, "docker", "compose", "-f", "ci/compose.yml", "up", "runner"
    )
    assert _statuses(results) == [V, V]


def test_compose_missing_file_option_is_broken(tmp_path):
    """-f pointing at a file that does not exist is broken."""
    results = _verify(tmp_path, "docker", "compose", "-f", "nope.yml", "up")
    assert B in _statuses(results)


def test_compose_include_makes_missing_service_unverifiable(tmp_path):
    """A compose include may hide more services."""
    _write(tmp_path, "compose.yml", "include:\n  - other.yml\nservices:\n  web: {}\n")
    assert _statuses(_verify(tmp_path, "docker", "compose", "up", "api")) == [U]


def test_compose_without_file_is_unverifiable(tmp_path):
    """No compose file means nothing to check against."""
    assert _statuses(_verify(tmp_path, "docker", "compose", "up", "web")) == [U]


def test_compose_down_names_no_services(tmp_path):
    """down does not take services, so there is nothing to verify."""
    _write(tmp_path, "compose.yml", COMPOSE)
    assert _statuses(_verify(tmp_path, "docker", "compose", "down")) == [U]


def test_compose_without_subcommand_is_unverifiable(tmp_path):
    """A bare 'docker compose' has no subcommand to verify."""
    _write(tmp_path, "compose.yml", COMPOSE)
    assert _statuses(_verify(tmp_path, "docker", "compose")) == [U]


def test_docker_run_is_not_a_compose_command(tmp_path):
    """docker run is third-party syntax and is not judged."""
    assert _statuses(_verify(tmp_path, "docker", "run", "-it", "ubuntu")) == [U]


def test_docker_rm_force_flag_is_not_a_file(tmp_path):
    """docker rm -f is a force flag, not a file argument."""
    assert _statuses(_verify(tmp_path, "docker", "rm", "-f", "web")) == [U]


def test_docker_build_file_option_is_path_checked(tmp_path):
    """docker build -f checks the Dockerfile exists."""
    assert B in _statuses(
        _verify(tmp_path, "docker", "build", "-f", "Dockerfile.x", ".")
    )
    _write(tmp_path, "Dockerfile", "FROM x\n")
    assert V in _statuses(_verify(tmp_path, "docker", "build", "-f", "Dockerfile", "."))


def test_invalid_compose_yaml_is_unverifiable(tmp_path):
    """An unreadable compose file is treated as absent."""
    _write(tmp_path, "compose.yml", "services: [unclosed")
    assert _statuses(_verify(tmp_path, "docker", "compose", "up", "web")) == [U]


# --- kubectl / helm file args ------------------------------------------------


def test_kubectl_apply_file_is_path_checked(tmp_path):
    """kubectl apply -f checks the manifest exists."""
    assert B in _statuses(_verify(tmp_path, "kubectl", "apply", "-f", "k8s/x.yaml"))
    _write(tmp_path, "k8s/x.yaml", "kind: Pod\n")
    assert V in _statuses(_verify(tmp_path, "kubectl", "apply", "-f", "k8s/x.yaml"))


def test_kubectl_logs_follow_is_not_a_file(tmp_path):
    """kubectl logs -f follows; it is not a file."""
    assert _statuses(_verify(tmp_path, "kubectl", "logs", "-f", "pod")) == [U]


def test_helm_values_equals_form_is_path_checked(tmp_path):
    """helm --values=path is checked for existence."""
    results = _verify(tmp_path, "helm", "install", "r", "c", "--values=v.yaml")
    assert B in _statuses(results)


# --- own CLI -----------------------------------------------------------------

CLI_SOURCE = (
    "import click\n"
    "@click.command()\n"
    '@click.option("--alpha", "-a")\n'
    '@click.option("--on/--off")\n'
    "def main(): pass\n"
)


def _own_cli(root: Path, source: str = CLI_SOURCE) -> None:
    """Create a package with a console script and the given CLI source."""
    _write(
        root,
        "pyproject.toml",
        '[tool.poetry.scripts]\nmytool = "mypkg.cli:main"\n',
    )
    _write(root, "mypkg/cli.py", source)


def test_own_cli_known_flag_is_verified(tmp_path):
    """A flag the console script defines is verified."""
    _own_cli(tmp_path)
    assert _statuses(_verify(tmp_path, "mytool", "--alpha", "1")) == [V]


def test_own_cli_unknown_flag_is_broken(tmp_path):
    """A flag the console script does not define is broken."""
    _own_cli(tmp_path)
    results = _verify(tmp_path, "mytool", "--beta")
    assert _statuses(results) == [B]
    assert "--beta" in results[0].reason


def test_own_cli_toggle_pair_and_equals_value(tmp_path):
    """--on/--off pairs and --flag=value forms are understood."""
    _own_cli(tmp_path)
    assert _statuses(_verify(tmp_path, "mytool", "--off", "--alpha=2")) == [V, V]


def test_own_cli_help_flag_is_always_valid(tmp_path):
    """--help is always accepted."""
    _own_cli(tmp_path)
    assert _statuses(_verify(tmp_path, "mytool", "--help")) == [V]


def test_own_cli_stops_at_double_dash(tmp_path):
    """Flags after -- are not checked."""
    _own_cli(tmp_path)
    assert _statuses(_verify(tmp_path, "mytool", "--", "--whatever")) == [U]


def test_own_cli_short_flags_are_not_judged(tmp_path):
    """Short flags are skipped; only long options are verified."""
    _own_cli(tmp_path)
    assert _statuses(_verify(tmp_path, "mytool", "-x")) == [U]


def test_own_cli_without_static_options_is_unverifiable(tmp_path):
    """If options cannot be read statically, the claim is unverifiable."""
    _own_cli(tmp_path, "def main(): pass\n")
    assert _statuses(_verify(tmp_path, "mytool", "--alpha")) == [U]


def test_own_cli_missing_module_is_unverifiable(tmp_path):
    """An entry point whose module is absent is unverifiable."""
    _write(tmp_path, "pyproject.toml", '[project.scripts]\nx = "nope.cli:main"\n')
    assert _statuses(_verify(tmp_path, "x", "--a")) == [U]


def test_own_cli_reads_project_scripts_and_src_layout(tmp_path):
    """[project.scripts] entries in a src/ layout are resolved."""
    _write(tmp_path, "pyproject.toml", '[project.scripts]\nx = "pkg.cli:main"\n')
    _write(tmp_path, "src/pkg/cli.py", CLI_SOURCE)
    assert _statuses(_verify(tmp_path, "x", "--alpha")) == [V]


def test_own_cli_package_init_module(tmp_path):
    """An entry point living in a package __init__ is resolved."""
    _write(tmp_path, "pyproject.toml", '[project.scripts]\nx = "pkg:main"\n')
    _write(tmp_path, "pkg/__init__.py", CLI_SOURCE)
    assert _statuses(_verify(tmp_path, "x", "--alpha")) == [V]


def test_invalid_pyproject_has_no_entry_points(tmp_path):
    """An unreadable pyproject.toml means no project scripts."""
    _write(tmp_path, "pyproject.toml", "= not toml")
    assert RepoFacts(tmp_path).entry_points() == {}


def test_static_flags_reads_argparse_add_argument():
    """argparse add_argument calls contribute options."""
    flags = _static_flags('p.add_argument("--name", "-n")\n')
    assert flags is not None and "--name" in flags


def test_static_flags_syntax_error_returns_none():
    """Unparseable source has no statically known options."""
    assert _static_flags("def (") is None


# --- python / shell / paths --------------------------------------------------


def test_python_script_exists_is_verified(tmp_path):
    """python script.py is verified when the script exists."""
    _write(tmp_path, "scripts/run.py", "")
    assert _statuses(_verify(tmp_path, "python", "scripts/run.py")) == [V]


def test_python_missing_script_is_broken(tmp_path):
    """python script.py is broken when the script is absent."""
    assert _statuses(_verify(tmp_path, "python3", "scripts/run.py")) == [B]


def test_python_module_in_repo_is_verified(tmp_path):
    """python -m of a local module is verified."""
    _write(tmp_path, "mypkg/__init__.py", "")
    _write(tmp_path, "mypkg/tool.py", "")
    assert _statuses(_verify(tmp_path, "python", "-m", "mypkg.tool")) == [V]


def test_python_missing_submodule_is_broken(tmp_path):
    """A missing submodule of a local package is broken."""
    _write(tmp_path, "mypkg/__init__.py", "")
    assert _statuses(_verify(tmp_path, "python", "-m", "mypkg.gone")) == [B]


def test_python_external_module_is_unverifiable(tmp_path):
    """python -m pytest is not a module of this repo."""
    assert _statuses(_verify(tmp_path, "python", "-m", "pytest")) == [U]


def test_python_inline_code_is_unverifiable(tmp_path):
    """python -c is not verified."""
    assert _statuses(_verify(tmp_path, "python", "-c", "print(1)")) == [U]


def test_python_without_script_is_unverifiable(tmp_path):
    """A bare python has nothing to verify."""
    assert _statuses(_verify(tmp_path, "python")) == [U]


def test_python_option_value_is_not_the_script(tmp_path):
    """python -W ignore script.py skips the warning filter value."""
    _write(tmp_path, "run.py", "")
    assert _statuses(_verify(tmp_path, "python", "-W", "ignore", "run.py")) == [V]


def test_bash_script_is_path_checked(tmp_path):
    """bash script.sh checks the script exists."""
    assert _statuses(_verify(tmp_path, "bash", "scripts/x.sh")) == [B]
    _write(tmp_path, "scripts/x.sh", "")
    assert _statuses(_verify(tmp_path, "bash", "scripts/x.sh")) == [V]


def test_bash_inline_code_is_unverifiable(tmp_path):
    """bash -c is not verified."""
    assert _statuses(_verify(tmp_path, "bash", "-c", "echo")) == [U]


def test_source_without_argument_is_unverifiable(tmp_path):
    """A bare source has nothing to verify."""
    assert _statuses(_verify(tmp_path, "source")) == [U]


def test_source_of_generated_dir_is_unverifiable(tmp_path):
    """source .venv/bin/activate points into a generated directory."""
    assert _statuses(_verify(tmp_path, "source", ".venv/bin/activate")) == [U]


def test_path_head_existing_is_verified(tmp_path):
    """./script that exists is verified."""
    _write(tmp_path, "run.sh", "")
    assert _statuses(_verify(tmp_path, "./run.sh")) == [V]


def test_path_head_missing_is_broken(tmp_path):
    """./script that does not exist is broken."""
    assert _statuses(_verify(tmp_path, "./run.sh")) == [B]


def test_path_head_in_generated_dir_is_unverifiable(tmp_path):
    """./build/app is a build output, so its absence is not broken."""
    assert _statuses(_verify(tmp_path, "./build/app")) == [U]


def test_path_outside_repo_is_unverifiable(tmp_path):
    """Paths that leave the repository are not judged."""
    assert _statuses(_verify(tmp_path, "../elsewhere/run.sh")) == [U]
    assert _statuses(_verify(tmp_path, "bash", "/usr/bin/x.sh")) == [U]
    assert _statuses(_verify(tmp_path, "bash", "~/x.sh")) == [U]


def test_path_with_glob_or_url_is_not_judged(tmp_path):
    """Globs and URLs yield no result, falling back to unverifiable."""
    assert _statuses(_verify(tmp_path, "bash", "scripts/*.sh")) == [U]
    assert _statuses(_verify(tmp_path, "bash", "https://x/y.sh")) == [U]
