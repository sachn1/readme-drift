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
    path = tmp_path / "README.md"
    path.write_text(README_CONTENT)
    return path


def test_finds_backtick_method(readme_file):
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert len(matches) >= 1
    assert any("connect" in m.matched_text for m in matches)


def test_finds_plain_function(readme_file):
    matches = find_symbol_in_readme(readme_file, "helper")
    assert len(matches) >= 1


def test_finds_plain_text_mention(readme_file):
    matches = find_symbol_in_readme(readme_file, "disconnect")
    assert len(matches) >= 1


def test_no_match_for_unknown_symbol(readme_file):
    matches = find_symbol_in_readme(readme_file, "nonexistent_function")
    assert matches == []


def test_scan_multiple_symbols(readme_file):
    results = scan_readme_for_symbols(
        readme_file,
        ["Client.connect", "helper", "nonexistent"],
    )
    assert "Client.connect" in results
    assert "helper" in results
    assert "nonexistent" not in results


def test_missing_readme(tmp_path):
    matches = find_symbol_in_readme(tmp_path / "README.md", "anything")
    assert matches == []


def test_match_includes_line_number(readme_file):
    matches = find_symbol_in_readme(readme_file, "Client.connect")
    assert all(m.line_number > 0 for m in matches)


def test_match_includes_line_text(readme_file):
    matches = find_symbol_in_readme(readme_file, "helper")
    assert all(len(m.line_text) > 0 for m in matches)


def test_at_most_one_match_per_line(readme_file):
    # The README has "Plain text mentions of disconnect are also caught."
    # which would match BOTH the backtick pattern AND the word-boundary pattern.
    # find_symbol_in_readme must return at most one ReadmeMatch per line.
    matches = find_symbol_in_readme(readme_file, "disconnect")
    line_numbers = [m.line_number for m in matches]
    assert len(line_numbers) == len(set(line_numbers)), "duplicate matches on same line"


def test_plain_text_false_skips_word_boundary(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Use disconnect to close the connection.\n")
    # The word appears as plain text, not in backticks — plain_text=False should miss it
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert matches == []


def test_plain_text_false_still_matches_backtick(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Call `disconnect` to close.\n")
    matches = find_symbol_in_readme(readme, "disconnect", plain_text=False)
    assert len(matches) == 1


def test_scan_readme_plain_text_false(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Use helper to process data.\n")
    results = scan_readme_for_symbols(readme, ["helper"], plain_text=False)
    assert "helper" not in results


def test_force_backtick_only_suppresses_plain_text_for_named_symbol(tmp_path):
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
    readme = tmp_path / "README.md"
    readme.write_text("Defined in `scripts.build` of package.json.\n")
    results = scan_readme_for_symbols(readme, ["scripts.build"])
    assert "scripts.build" in results


def test_scan_key_path_dotnotation_plain_text(tmp_path):
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
```
"""


def test_mermaid_class_diagram_matches_class_name(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(MERMAID_CLASS_DIAGRAM)
    matches = find_symbol_in_readme(readme, "Client")
    assert matches


def test_mermaid_class_diagram_matches_method_name(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(MERMAID_CLASS_DIAGRAM)
    matches = find_symbol_in_readme(readme, "disconnect")
    assert matches


def test_mermaid_class_diagram_bypasses_plain_text_false(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(MERMAID_CLASS_DIAGRAM)
    # plain_text=False would normally suppress non-backtick matches, but
    # mermaid class-diagram content is a high-trust surface like backticks.
    matches = find_symbol_in_readme(readme, "Client", plain_text=False)
    assert matches


def test_mermaid_class_diagram_bypasses_noise_blocklist(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(MERMAID_CLASS_DIAGRAM)
    # "connect" would be suppressed as plain text under noise/short-symbol
    # rules via force_backtick_only, but should still match inside the block.
    results = scan_readme_for_symbols(
        readme,
        ["connect"],
        plain_text=True,
        force_backtick_only={"connect"},
    )
    assert "connect" in results


def test_non_class_diagram_mermaid_block_not_treated_as_high_trust(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "```mermaid\nflowchart LR\n    A --> deploy\n```\n"
    )
    # "deploy" appears inside a mermaid block, but it's a flowchart, not a
    # classDiagram — must not bypass noise suppression.
    results = scan_readme_for_symbols(
        readme,
        ["deploy"],
        plain_text=True,
        force_backtick_only={"deploy"},
    )
    assert "deploy" not in results


def test_mermaid_matching_does_not_leak_outside_fence(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "Mentions build outside any fence.\n\n"
        "```mermaid\nclassDiagram\n    class Foo\n```\n"
    )
    # "build" never appears inside the classDiagram fence, so noise
    # suppression should still apply to its outside-fence mention.
    results = scan_readme_for_symbols(
        readme,
        ["build"],
        plain_text=True,
        force_backtick_only={"build"},
    )
    assert "build" not in results


def test_find_mermaid_class_diagram_lines_helper():
    from readme_drift.scanner import _find_mermaid_class_diagram_lines

    lines = MERMAID_CLASS_DIAGRAM.splitlines()
    result = _find_mermaid_class_diagram_lines(lines)
    # Lines inside the fence (classDiagram through the closing brace) are
    # included; the fence markers themselves and content outside are not.
    for i, line in enumerate(lines, start=1):
        if line.strip() in ("classDiagram", "class Client {", "+connect(host, port)", "+disconnect()", "}"):
            assert i in result, f"expected line {i} ({line!r}) in result"
    assert 1 not in result  # title, outside any fence
