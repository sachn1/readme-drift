"""Enforce the project docstring convention across source and tests."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILES = sorted((ROOT / "readme_drift").glob("*.py"))
TEST_FILES = sorted((ROOT / "tests").glob("*.py"))


def _functions_and_classes(tree: ast.Module):
    """Yield (node, qualname, in_function) for every def and class in a module."""
    stack: list[tuple[ast.AST, str, bool]] = [(tree, "", False)]
    while stack:
        parent, prefix, in_func = stack.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                yield child, qual, in_func
                nested_in_func = in_func or not isinstance(child, ast.ClassDef)
                stack.append((child, qual + ".", nested_in_func))


def _is_property(node: ast.AST) -> bool:
    """Return True if a function is decorated as a property."""
    decorators = getattr(node, "decorator_list", [])
    return any(
        (isinstance(d, ast.Name) and d.id == "property")
        or (isinstance(d, ast.Attribute) and d.attr in {"setter", "getter"})
        for d in decorators
    )


def _has_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if a function takes anything besides self or cls."""
    a = node.args
    names = [x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]]
    names = [n for n in names if n not in {"self", "cls"}]
    return bool(names or a.vararg or a.kwarg)


def _returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the annotation says the function returns something."""
    ann = node.returns
    return ann is not None and not (isinstance(ann, ast.Constant) and ann.value is None)


def _violations(path: Path, *, is_test: bool) -> list[str]:
    """Collect docstring convention violations for one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    rel = path.relative_to(ROOT)

    module_doc = ast.get_docstring(tree)
    if not module_doc:
        problems.append(f"{rel}: module docstring missing")
    elif "\n" in module_doc:
        problems.append(f"{rel}: module docstring must be one line")

    for node, qual, in_func in _functions_and_classes(tree):
        where = f"{rel}:{node.lineno} {qual}"
        doc = ast.get_docstring(node)
        is_class = isinstance(node, ast.ClassDef)
        name = node.name
        is_dunder = name.startswith("__") and name.endswith("__")
        is_private = name.startswith("_") and not is_dunder

        one_line_required = is_class or is_test or is_private or is_dunder
        if one_line_required:
            if is_dunder and not doc:
                continue
            if not doc:
                problems.append(f"{where}: docstring missing")
            elif "\n" in doc:
                problems.append(f"{where}: docstring must be one line")
            continue

        # Public function or method in the package: numpy format.
        if in_func or _is_property(node):
            if doc and "\n" in doc:
                problems.append(f"{where}: docstring must be one line")
            continue
        if not doc:
            problems.append(f"{where}: docstring missing")
            continue
        if _has_params(node) and "Parameters\n----------" not in doc:
            problems.append(f"{where}: numpy 'Parameters' section missing")
        if _returns_value(node) and "Returns\n-------" not in doc:
            problems.append(f"{where}: numpy 'Returns' section missing")
    return problems


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_source_docstrings_follow_convention(path):
    """Source docstrings follow the numpy / one-line convention."""
    assert _violations(path, is_test=False) == []


@pytest.mark.parametrize("path", TEST_FILES, ids=lambda p: p.name)
def test_test_docstrings_follow_convention(path):
    """Test module, functions and helpers all carry one-line docstrings."""
    assert _violations(path, is_test=True) == []
