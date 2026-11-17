"""Tests for README scanner module."""

from pathlib import Path

import pytest

from readme_drift.scanner import find_symbol_in_readme, scan_readme_for_symbols

README_CONTENT = """# My Library

Use `Client.connect(host, port)` to establish a connection.
Then call `Client.disconnect()` when done.

The `helper` function is also available.

For advanced use, see `Client.from_config`.

Plain text mentions of disconnect are also caught.
"""


@pytest.fixture
def readme_file(tmp_path) -> Path:
    """Provide a temporary README.md containing the sample content."""
    path = tmp_path / "README.md"
    path.write_text(README_CONTENT)
    return path


def test_finds_backtick_method(readme_file):
    """Finds backtick method."""
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert len(matches) >= 1
    assert any("connect" in m.matched_text for m in matches)


def test_finds_plain_function(readme_file):
    """Finds plain function."""
    matches = find_symbol_in_readme(readme_file, "helper")
    assert len(matches) >= 1


def test_finds_plain_text_mention(readme_file):
    """Finds plain text mention."""
    matches = find_symbol_in_readme(readme_file, "disconnect")
    assert len(matches) >= 1


def test_no_match_for_unknown_symbol(readme_file):
    """No match for unknown symbol."""
    matches = find_symbol_in_readme(readme_file, "nonexistent_function")
    assert matches == []


def test_scan_multiple_symbols(readme_file):
    """Scan multiple symbols."""
    results = scan_readme_for_symbols(
        readme_file,
        ["Client.connect", "helper", "nonexistent"],
    )
    assert "Client.connect" in results
    assert "helper" in results
    assert "nonexistent" not in results


def test_missing_readme(tmp_path):
    """Missing README."""
    matches = find_symbol_in_readme(tmp_path / "README.md", "anything")
    assert matches == []


def test_match_includes_line_number(readme_file):
    """Match includes line number."""
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert all(m.line_number > 0 for m in matches)


def test_match_includes_line_text(readme_file):
    """Match includes line text."""
    matches = find_symbol_in_readme(readme_file, "helper")
    assert all(len(m.line_text) > 0 for m in matches)


def test_at_most_one_match_per_line(readme_file):
    # The README has "Plain text mentions of disconnect are also caught."
    # which would match BOTH the backtick pattern AND the word-boundary pattern.
    # find_symbol_in_readme must return at most one ReadmeMatch per line.
    """At most one match per line."""
    matches = find_symbol_in_readme(readme_file, "disconnect")
    line_numbers = [m.line_number for m in matches]
    assert len(line_numbers) == len(set(line_numbers)), "duplicate matches on same line"


def test_plain_text_false_skips_word_boundary(tmp_path):
    """Plain text false skips word boundary."""
    readme = tmp_path / "README.md"
    readme.write_text("Use disconnect to close the connection.\n")
    # The word appears as plain text, not in backticks — plain_text=False should miss it
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert matches == []


def test_plain_text_false_still_matches_backtick(tmp_path):
    """Plain text false still matches backtick."""
    readme = tmp_path / "README.md"
    readme.write_text("Call `disconnect` to close.\n")
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert len(matches) == 1


def test_scan_readme_plain_text_false(tmp_path):
    """Scan README plain text false."""
    readme = tmp_path / "README.md"
    readme.write_text("Use helper to process data.\n")
    results = scan_readme_for_symbols(readme, ["helper"], plain_text=False)
    assert "helper" not in results


def test_force_backtick_only_suppresses_plain_text_for_named_symbol(tmp_path):
    """Force backtick only suppresses plain text for named symbol."""
    readme = tmp_path / "README.md"
    readme.write_text("Run the build step before deploying.\n")
    # "build" appears as plain text only.  With force_backtick_only it should not match.
    results = scan_readme_for_symbols(
        readme,
        ["build"],
        plain_text=True,
        force_backtick_only={"build"},
    )
    assert "build" not in results


def test_force_backtick_only_still_matches_backtick(tmp_path):
    """Force backtick only still matches backtick."""
    readme = tmp_path / "README.md"
    readme.write_text("Run `build` to compile.\n")
    results = scan_readme_for_symbols(
        readme,
        ["build"],
        plain_text=True,
        force_backtick_only={"build"},
    )
    assert "build" in results


def test_force_backtick_only_does_not_affect_other_symbols(tmp_path):
    """Force backtick only does not affect other symbols."""
    readme = tmp_path / "README.md"
    readme.write_text("Run the build step. Call connect to link.\n")
    # "build" is in force_backtick_only, "connect" is not.
    results = scan_readme_for_symbols(
        readme,
        ["build", "connect"],
        plain_text=True,
        force_backtick_only={"build"},
    )
    assert "build" not in results  # plain text suppressed
    assert "connect" in results  # plain text still active


def test_force_backtick_only_none_behaves_normally(tmp_path):
    """Force backtick only none behaves normally."""
    readme = tmp_path / "README.md"
    readme.write_text("Run the build step.\n")
    results = scan_readme_for_symbols(
        readme,
        ["build"],
        plain_text=True,
        force_backtick_only=None,  # default — no override
    )
    assert "build" in results


def test_scan_key_path_dotnotation_in_backtick(tmp_path):
    """Scan key path dotnotation in backtick."""
    readme = tmp_path / "README.md"
    readme.write_text("Defined in `scripts.build` of package.json.\n")
    results = scan_readme_for_symbols(readme, ["scripts.build"])
    assert "scripts.build" in results


def test_scan_key_path_dotnotation_plain_text(tmp_path):
    """Scan key path dotnotation plain text."""
    readme = tmp_path / "README.md"
    readme.write_text("The scripts.build target compiles the project.\n")
    results = scan_readme_for_symbols(readme, ["scripts.build"], plain_text=True)
    assert "scripts.build" in results


# --- mermaid classDiagram matching ------------------------------------------

MERMAID_CLASS_DIAGRAM = """# My Library

```mermaid
classDiagram
    class Client {
        +connect(host, port)
        +disconnect()
    }
    class Job {
        +run()
    }
```
"""


def _readme(tmp_path, text):
    """Write text to a README in tmp_path and return its path."""
    path = tmp_path / "README.md"
    path.write_text(text)
    return path


def _scan(path, symbol, **kwargs):
    """Scan a README for one symbol and return its matches."""
    return scan_readme_for_symbols(path, [symbol], **kwargs).get(symbol, [])


def test_mermaid_class_name_matches_its_class(tmp_path):
    """A bare class name matches the class in a classDiagram."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    assert _scan(readme, "Client")


def test_mermaid_method_matches_inside_its_own_class(tmp_path):
    """Class.method matches the member line of that class."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    matches = _scan(readme, "Client.disconnect")
    assert [m.line_text for m in matches] == ["+disconnect()"]


def test_mermaid_method_does_not_match_a_different_class(tmp_path):
    """Job.connect must not match Client's +connect() line."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    assert _scan(readme, "Job.connect") == []


def test_mermaid_method_match_ignores_noise_and_plain_text_settings(tmp_path):
    """A scoped method match bypasses noise suppression and plain_text=False."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    matches = _scan(
        readme, "Job.run", plain_text=False, force_backtick_only={"Job.run"}
    )
    assert [m.line_text for m in matches] == ["+run()"]


def test_mermaid_class_name_ignores_noise_and_plain_text_settings(tmp_path):
    """A class name match bypasses noise suppression and plain_text=False."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    assert _scan(readme, "Job", plain_text=False, force_backtick_only={"Job"})


def test_mermaid_bare_function_name_does_not_match_member_lines(tmp_path):
    """A removed top-level function must not match a class's +run() member."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    assert _scan(readme, "run", plain_text=False, force_backtick_only={"run"}) == []


def test_mermaid_bare_name_does_not_match_a_relationship_label(tmp_path):
    """A function named like a relationship label is not a class, so it is not matched."""
    readme = _readme(
        tmp_path,
        "```mermaid\nclassDiagram\n    class Client\n    class Job\n"
        "    Client --> Job : run\n```\n",
    )
    assert _scan(readme, "run", plain_text=False, force_backtick_only={"run"}) == []


def test_mermaid_config_key_does_not_match_a_member_attribute(tmp_path):
    """A config key called name must not match a +name attribute in a diagram."""
    readme = _readme(
        tmp_path,
        "```mermaid\nclassDiagram\n    class User {\n        +name: str\n    }\n```\n",
    )
    assert _scan(readme, "name", force_backtick_only={"name"}) == []


def test_mermaid_dotted_config_path_does_not_match(tmp_path):
    """A dotted config path whose first part is not a class never matches."""
    readme = _readme(tmp_path, MERMAID_CLASS_DIAGRAM)
    assert _scan(readme, "scripts.run", force_backtick_only={"scripts.run"}) == []


def test_mermaid_colon_member_syntax_is_scoped_to_its_class(tmp_path):
    """The `Class : +member` form belongs to the named class only."""
    readme = _readme(
        tmp_path,
        "```mermaid\nclassDiagram\n    Client : +connect()\n    Job : +stop()\n```\n",
    )
    assert _scan(readme, "Client.connect", plain_text=False)
    assert _scan(readme, "Job.connect", plain_text=False) == []


def test_mermaid_class_defined_only_by_a_relationship_is_matched(tmp_path):
    """A class that only appears as a relationship endpoint still counts."""
    readme = _readme(tmp_path, "```mermaid\nclassDiagram\n    Animal <|-- Duck\n```\n")
    assert _scan(readme, "Duck", plain_text=False, force_backtick_only={"Duck"})


def test_mermaid_multiple_diagrams_are_each_parsed(tmp_path):
    """Names in a second classDiagram are matched independently of the first."""
    readme = _readme(
        tmp_path,
        "```mermaid\nclassDiagram\n    class Alpha {\n        +go()\n    }\n```\n\n"
        "```mermaid\nclassDiagram\n    class Beta {\n        +stop()\n    }\n```\n",
    )
    assert _scan(readme, "Beta.stop", plain_text=False)
    assert _scan(readme, "Alpha.stop", plain_text=False) == []


def test_non_class_diagram_mermaid_block_is_not_structural(tmp_path):
    """A flowchart gets ordinary prose matching, so noise suppression applies."""
    readme = _readme(tmp_path, "```mermaid\nflowchart LR\n    A --> deploy\n```\n")
    assert _scan(readme, "deploy", force_backtick_only={"deploy"}) == []


def test_mermaid_matching_does_not_leak_outside_fence(tmp_path):
    """A name mentioned outside any fence keeps normal noise suppression."""
    readme = _readme(
        tmp_path,
        "Mentions Job outside any fence.\n\n"
        "```mermaid\nclassDiagram\n    class Foo\n```\n",
    )
    assert _scan(readme, "Job", force_backtick_only={"Job"}) == []


def test_parse_class_diagrams_records_classes_owners_and_lines():
    """The parser exposes declared classes, member owners and block line numbers."""
    from readme_drift.scanner import _parse_class_diagrams

    lines = MERMAID_CLASS_DIAGRAM.splitlines()
    (diagram,) = _parse_class_diagrams(lines)
    assert diagram.classes == {"Client", "Job"}
    owner_by_text = {lines[n - 1].strip(): o for n, o in diagram.owners.items()}
    assert owner_by_text == {
        "+connect(host, port)": "Client",
        "+disconnect()": "Client",
        "+run()": "Job",
    }
    assert 1 not in diagram.lines  # title, outside the fence


# --- code-only symbols (config keys, Makefile targets) ----------------------


def _scan_code_only(tmp_path, text, symbol):
    """Scan a README for a symbol that may match only in code."""
    readme = _readme(tmp_path, text)
    return scan_readme_for_symbols(readme, [symbol], code_only_symbols={symbol}).get(
        symbol, []
    )


def test_code_only_symbol_matches_anywhere_inside_an_inline_span(tmp_path):
    """A name inside `make deploy` matches although the span starts with make."""
    assert _scan_code_only(tmp_path, "Run `make deploy` to ship.\n", "deploy")


def test_code_only_symbol_ignores_plain_prose(tmp_path):
    """The same word in ordinary prose does not match."""
    assert (
        _scan_code_only(tmp_path, "We include percentage complete.\n", "include") == []
    )


def test_code_only_symbol_ignores_text_between_two_spans(tmp_path):
    """Prose between two inline spans is not treated as code."""
    assert _scan_code_only(tmp_path, "`a` deploy `b`\n", "deploy") == []


def test_code_only_symbol_matches_inside_a_fenced_block(tmp_path):
    """A name on a line inside a fenced block matches."""
    text = "```bash\nmake deploy now\n```\n"
    assert [m.line_number for m in _scan_code_only(tmp_path, text, "deploy")] == [2]


def test_code_only_symbol_ignores_prose_around_a_fence(tmp_path):
    """Prose before and after a fenced block is still prose."""
    text = "deploy first\n```bash\nls\n```\ndeploy last\n"
    assert _scan_code_only(tmp_path, text, "deploy") == []


def test_code_only_symbol_works_with_tilde_fences(tmp_path):
    """A tilde fence counts as code too."""
    assert _scan_code_only(tmp_path, "~~~\nmake deploy\n~~~\n", "deploy")


def test_code_only_symbol_still_matches_a_span_that_starts_with_it(tmp_path):
    """The original backtick rule keeps working for code-only symbols."""
    assert _scan_code_only(tmp_path, "Use `deploy` to ship.\n", "deploy")


def test_force_backtick_only_wins_over_code_only(tmp_path):
    """A noise-listed symbol keeps the stricter span-start rule."""
    readme = _readme(tmp_path, "Run `make build` now.\n")
    hits = scan_readme_for_symbols(
        readme, ["build"], force_backtick_only={"build"}, code_only_symbols={"build"}
    )
    assert hits == {}


def test_code_only_symbol_ignores_comments_inside_a_fenced_block(tmp_path):
    """A comment line or trailing comment in a code block is prose, not code."""
    text = (
        "```toml\n# dependency with extras\nfoo = 1  # extras here\nextras = 2\n```\n"
    )
    assert [m.line_number for m in _scan_code_only(tmp_path, text, "extras")] == [4]


# --- backtick spans match the whole name, not a prefix ------------------------


def _ticked(tmp_path, text, symbol):
    """Return matches for a symbol in backticks only (plain-text matching off)."""
    readme = _readme(tmp_path, text)
    return scan_readme_for_symbols(readme, [symbol], plain_text=False).get(symbol, [])


def test_backtick_span_with_a_longer_identifier_is_not_a_match(tmp_path):
    """`get_extra_info(info)` is not a reference to `get`."""
    assert _ticked(tmp_path, "* `get_extra_info(info) -> Any`\n", "get") == []


def test_backtick_span_of_a_prefixed_name_is_not_a_match(tmp_path):
    """`connection_pool` is not a reference to `connect`."""
    assert _ticked(tmp_path, "See `connection_pool` here.\n", "connect") == []


def test_backtick_span_of_a_plural_library_name_is_not_a_match(tmp_path):
    """`requests` is not a reference to `request`."""
    assert _ticked(tmp_path, "Built on `requests`.\n", "request") == []


def test_backtick_span_with_a_hyphenated_longer_name_is_not_a_match(tmp_path):
    """`lint-docs` is not a reference to `lint`."""
    assert _ticked(tmp_path, "Run `lint-docs`.\n", "lint") == []


def test_backtick_span_with_arguments_is_a_match(tmp_path):
    """`connect(host, port)` is a reference to `connect`."""
    assert _ticked(tmp_path, "Call `connect(host, port)`.\n", "connect")


def test_backtick_span_that_is_exactly_the_name_is_a_match(tmp_path):
    """`connect` is a reference to `connect`."""
    assert _ticked(tmp_path, "Call `connect` first.\n", "connect")


def test_backtick_span_for_a_dotted_symbol_with_a_call_is_a_match(tmp_path):
    """`Client.connect()` is a reference to `Client.connect`."""
    assert _ticked(tmp_path, "Use `Client.connect()` now.\n", "Client.connect")


def test_backtick_span_with_an_attribute_after_the_name_is_a_match(tmp_path):
    """`connect.timeout` still starts with the whole name `connect`."""
    assert _ticked(tmp_path, "Set `connect.timeout`.\n", "connect")
