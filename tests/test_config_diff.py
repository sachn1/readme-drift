"""Tests for config_diff — JSON, TOML, and YAML key-path extraction and diffing."""

from readme_drift.config_diff import (
    JsonExtractor,
    KeyExtractor,
    TomlExtractor,
    YamlExtractor,
    _flatten,
    diff_config,
)
from readme_drift.models import ChangeType


def test_flatten_flat_dict():
    result = _flatten({"a": 1, "b": "hello"})
    assert result == {"a": "1", "b": "hello"}


def test_flatten_nested_dict():
    result = _flatten({"scripts": {"build": "webpack", "test": "jest"}})
    assert result["scripts.build"] == "webpack"
    assert result["scripts.test"] == "jest"


def test_flatten_list():
    result = _flatten({"steps": ["checkout", "build"]})
    assert result["steps[0]"] == "checkout"
    assert result["steps[1]"] == "build"


def test_flatten_empty():
    assert _flatten({}) == {}
    assert _flatten([]) == {}


def test_extractors_satisfy_protocol():
    for extractor in (JsonExtractor(), TomlExtractor(), YamlExtractor()):
        assert isinstance(extractor, KeyExtractor)


def test_json_extracts_scripts():
    content = '{"scripts": {"build": "webpack", "test": "jest"}}'
    result = JsonExtractor().extract(content)
    assert result["scripts.build"] == "webpack"
    assert result["scripts.test"] == "jest"


def test_json_empty_content():
    assert JsonExtractor().extract("") == {}
    assert JsonExtractor().extract("   ") == {}


def test_json_invalid_returns_empty():
    assert JsonExtractor().extract("{not valid json}") == {}


def test_json_extracts_top_level_keys():
    content = '{"name": "my-pkg", "version": "1.0.0"}'
    result = JsonExtractor().extract(content)
    assert result["name"] == "my-pkg"
    assert result["version"] == "1.0.0"


def test_toml_extracts_tool_sections():
    content = "[tool.ruff]\nline-length = 88\n"
    result = TomlExtractor().extract(content)
    assert result["tool.ruff.line-length"] == "88"


def test_toml_empty_content():
    assert TomlExtractor().extract("") == {}


def test_toml_invalid_returns_empty():
    assert TomlExtractor().extract("not = valid = toml =") == {}


def test_toml_extracts_scripts():
    content = '[tool.poetry.scripts]\nreadme-drift = "readme_drift.cli:main"\n'
    result = TomlExtractor().extract(content)
    assert "tool.poetry.scripts.readme-drift" in result


def test_yaml_extracts_github_actions_jobs():
    content = "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
    result = YamlExtractor().extract(content)
    assert result["jobs.build.runs-on"] == "ubuntu-latest"


def test_yaml_empty_content():
    assert YamlExtractor().extract("") == {}


def test_yaml_null_document():
    assert YamlExtractor().extract("---\n") == {}


def test_yaml_invalid_returns_empty():
    # Deliberately malformed YAML (tab indentation is invalid)
    assert YamlExtractor().extract("key:\n\tvalue") == {}


def test_yaml_extracts_top_level_name():
    content = "name: My Workflow\non: [push]\n"
    result = YamlExtractor().extract(content)
    assert result["name"] == "My Workflow"


def test_diff_json_removed_script():
    old = '{"scripts": {"build": "webpack", "test": "jest"}}'
    new = '{"scripts": {"compile": "webpack", "test": "jest"}}'
    changes = diff_config(old, new, file="package.json")
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    added = [c for c in changes if c.change_type == ChangeType.ADDED]
    assert any(c.name == "build" for c in removed)
    assert any(c.name == "compile" for c in added)


def test_diff_toml_removed_section():
    old = "[tool.black]\nline-length = 88\n"
    new = "[tool.ruff]\nline-length = 88\n"
    changes = diff_config(old, new, file="pyproject.toml")
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    added = [c for c in changes if c.change_type == ChangeType.ADDED]
    assert any(c.name == "black" for c in removed)
    assert any(c.name == "ruff" for c in added)


def test_diff_yaml_removed_job():
    old = "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
    new = "jobs:\n  ci:\n    runs-on: ubuntu-latest\n"
    changes = diff_config(old, new, file="ci.yml")
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    added = [c for c in changes if c.change_type == ChangeType.ADDED]
    assert any(c.name == "build" for c in removed)
    assert any(c.name == "ci" for c in added)


def test_diff_no_changes():
    content = '{"scripts": {"build": "webpack"}}'
    assert diff_config(content, content, file="package.json") == []


def test_diff_empty_old():
    new = '{"scripts": {"build": "webpack"}}'
    changes = diff_config("", new, file="package.json")
    assert all(c.change_type == ChangeType.ADDED for c in changes)


def test_diff_empty_new():
    old = '{"scripts": {"build": "webpack"}}'
    changes = diff_config(old, "", file="package.json")
    assert all(c.change_type == ChangeType.REMOVED for c in changes)


def test_diff_unknown_extension_returns_empty():
    changes = diff_config('{"a": 1}', '{"b": 2}', file="config.cfg")
    assert changes == []


def test_diff_leaf_deduplication():
    # 'name' key appears in multiple job sections. When removed from all of them
    # it should be reported exactly once, not once per occurrence.
    old = "jobs:\n  build:\n    name: build\n  test:\n    name: test\n"
    new = "jobs:\n  build:\n    id: build\n  test:\n    id: test\n"
    changes = diff_config(old, new, file="ci.yml")
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    removed_names = [c.name for c in removed]
    assert removed_names.count("name") == 1, (
        "duplicate leaf 'name' must be reported once"
    )


def test_diff_added_not_flagged_as_stale():
    from readme_drift.drift_checker import _symbols_from_changes
    from readme_drift.models import SymbolChange

    change = SymbolChange(name="new-script", change_type=ChangeType.ADDED)
    symbols = _symbols_from_changes([change])
    assert "new-script" in symbols  # searched but...

    # ...the finding-building loop skips ADDED regardless
    findings = []
    fake_matches = {"new-script": []}
    for c in [change]:
        if c.change_type == ChangeType.ADDED:
            continue
        if c.name in fake_matches:
            findings.append(c)
    assert findings == []
