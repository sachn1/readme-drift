"""Tests for extracting shell-command claims from README code blocks."""

from readme_drift.claims import IGNORE_MARKER, extract_claims


def _claims(tmp_path, text):
    """Write a README with the given text and return its extracted claims."""
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    return extract_claims(path)


def _raws(claims):
    """Return the raw command text of each claim."""
    return [c.raw for c in claims]


def test_extracts_commands_from_bash_block_with_line_numbers(tmp_path):
    """Commands in a bash fence become claims with 1-indexed line numbers."""
    claims = _claims(tmp_path, "intro\n\n```bash\nmake lint\nmake test\n```\n")
    assert _raws(claims) == ["make lint", "make test"]
    assert [c.line_number for c in claims] == [4, 5]
    assert claims[0].head == "make"
    assert claims[0].args == ("lint",)


def test_missing_readme_returns_no_claims(tmp_path):
    """A README that does not exist yields no claims."""
    assert extract_claims(tmp_path / "README.md") == []


def test_non_shell_fences_are_ignored(tmp_path):
    """Python, YAML and other tagged fences are not read as shell."""
    text = "```python\nmake lint\n```\n\n```yaml\nmake test: x\n```\n"
    assert _claims(tmp_path, text) == []


def test_untagged_fence_is_read_as_shell(tmp_path):
    """An untagged fence is treated as shell."""
    assert _raws(_claims(tmp_path, "```\nmake lint\n```\n")) == ["make lint"]


def test_brace_style_info_string_is_not_shell(tmp_path):
    """A fence with an unrecognized info string such as {.python} is skipped."""
    assert _claims(tmp_path, "```{.python}\nmake lint\n```\n") == []


def test_tilde_fence_is_supported(tmp_path):
    """A ~~~ fence is read like a backtick fence."""
    assert _raws(_claims(tmp_path, "~~~sh\nmake lint\n~~~\n")) == ["make lint"]


def test_longer_fence_is_not_closed_by_shorter_one(tmp_path):
    """A four-backtick fence stays open across an inner three-backtick line."""
    text = "````bash\nmake a\n```\nmake b\n````\n"
    assert _raws(_claims(tmp_path, text)) == ["make a", "make b"]


def test_prompt_is_stripped_in_bash_block(tmp_path):
    """A leading '$ ' prompt is removed from commands."""
    assert _raws(_claims(tmp_path, "```bash\n$ make lint\n```\n")) == ["make lint"]


def test_console_block_only_reads_prompted_lines(tmp_path):
    """In a console fence, lines without a '$ ' prompt are output, not commands."""
    text = "```console\n$ make lint\nok: 3 passed\n$ make test\n```\n"
    assert _raws(_claims(tmp_path, text)) == ["make lint", "make test"]


def test_comment_lines_are_skipped(tmp_path):
    """Lines starting with # are comments."""
    assert _raws(_claims(tmp_path, "```bash\n# install\nmake lint\n```\n")) == [
        "make lint"
    ]


def test_backslash_continuation_is_joined(tmp_path):
    """A command continued with a trailing backslash is one claim."""
    text = "```bash\nreadme-drift \\\n  --staged \\\n  --verify\n```\n"
    claims = _claims(tmp_path, text)
    assert len(claims) == 1
    assert claims[0].args == ("--staged", "--verify")
    assert claims[0].line_number == 2


def test_chained_commands_are_split(tmp_path):
    """&&, ; and | split one line into separate claims."""
    claims = _claims(tmp_path, "```bash\nmake lint && make test; echo hi | cat\n```\n")
    assert _raws(claims) == ["make lint", "make test", "echo hi", "cat"]


def test_redirections_are_dropped(tmp_path):
    """Redirections and their targets are not arguments."""
    claims = _claims(tmp_path, "```bash\nmake test > out.txt 2>&1\n```\n")
    assert claims[0].args == ("test",)


def test_env_assignments_and_wrappers_are_stripped(tmp_path):
    """Env assignments, sudo and poetry run prefixes are removed from the head."""
    text = "```bash\nFOO=1 sudo make lint\npoetry run readme-drift --init\n```\n"
    claims = _claims(tmp_path, text)
    assert [c.head for c in claims] == ["make", "readme-drift"]


def test_placeholder_arguments_are_dropped(tmp_path):
    """<name>, $VAR and ... tokens are removed from the arguments."""
    claims = _claims(tmp_path, "```bash\nmake <target> $VAR ... build\n```\n")
    assert claims[0].args == ("build",)


def test_placeholder_head_skips_the_command(tmp_path):
    """A command whose head is a placeholder yields no claim."""
    assert _claims(tmp_path, "```bash\n$CMD --flag\n<tool> run\n```\n") == []


def test_non_command_heads_are_skipped(tmp_path):
    """Lines that do not start with a command-like word are not claims."""
    assert _claims(tmp_path, "```\n→ Please update\n• item\n```\n") == []


def test_ignore_marker_before_fence_skips_block(tmp_path):
    """The ignore marker above a fence skips the whole block."""
    text = f"{IGNORE_MARKER}\n```bash\nmake nope\n```\n\n```bash\nmake yes\n```\n"
    assert _raws(_claims(tmp_path, text)) == ["make yes"]


def test_ignore_marker_allows_blank_line_before_fence(tmp_path):
    """A blank line between the marker and the fence is tolerated."""
    text = f"{IGNORE_MARKER}\n\n```bash\nmake nope\n```\n"
    assert _claims(tmp_path, text) == []


def test_ignore_marker_inside_block_skips_next_command_only(tmp_path):
    """A marker line inside a block skips only the command after it."""
    text = f"```bash\n{IGNORE_MARKER}\nmake nope\nmake yes\n```\n"
    assert _raws(_claims(tmp_path, text)) == ["make yes"]


def test_cd_marks_later_commands(tmp_path):
    """Commands after cd in a block are flagged as running elsewhere."""
    claims = _claims(tmp_path, "```bash\nmake a\ncd sub\nmake b\n```\n")
    assert [c.cwd_changed for c in claims] == [False, False, True]


def test_cd_state_resets_per_block(tmp_path):
    """The cd flag does not leak into the next fence."""
    text = "```bash\ncd sub\n```\n\n```bash\nmake b\n```\n"
    assert _claims(tmp_path, text)[-1].cwd_changed is False


def test_heredoc_body_is_skipped(tmp_path):
    """Lines inside a heredoc are not read as commands."""
    text = "```bash\ncat <<EOF\nmake fake\nEOF\nmake real\n```\n"
    assert _raws(_claims(tmp_path, text)) == ["cat", "make real"]


def test_unparseable_line_is_skipped(tmp_path):
    """A line with an unbalanced quote yields no claim but does not stop parsing."""
    claims = _claims(tmp_path, "```bash\necho 'oops\nmake ok\n```\n")
    assert _raws(claims) == ["make ok"]
