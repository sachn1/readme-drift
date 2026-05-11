"""AST-based diffing to extract changed public symbols between two code versions."""

import ast

from .models import ChangeType, PublicAPI, SymbolChange


def _is_public(name: str) -> bool:
    """Determine if a name is public (does not start with an underscore)."""
    return not name.startswith("_")


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Format a function/method signature as a readable string."""
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    args = []
    func_args = node.args

    # Positional args
    num_defaults = len(func_args.defaults)
    num_args = len(func_args.args)
    for i, arg in enumerate(func_args.args):
        if arg.arg == "self" or arg.arg == "cls":
            continue
        default_index = i - (num_args - num_defaults)
        if default_index >= 0:
            default = func_args.defaults[default_index]
            args.append(f"{arg.arg}={ast.unparse(default)}")
        else:
            args.append(arg.arg)

    # *args
    if func_args.vararg:
        args.append(f"*{func_args.vararg.arg}")

    # **kwargs
    if func_args.kwarg:
        args.append(f"**{func_args.kwarg.arg}")

    return f"{node.name}({', '.join(args)})"


def extract_public_api(source: str) -> PublicAPI:
    """Parse Python source and extract the public API surface.

    Parameters
    ----------
    source : str
        The source code of a Python module.

    Returns
    -------
    PublicAPI
        An object containing the public functions, classes, and methods defined in the source.
    """
    if not source.strip():
        return PublicAPI()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return PublicAPI()

    api = PublicAPI()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_public(node.name):
            method_sigs: set[str] = set()
            for item in node.body:
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and _is_public(item.name):
                    sig = _format_signature(item)
                    method_sigs.add(sig)
                    api.methods[f"{node.name}.{item.name}"] = sig
            api.classes[node.name] = method_sigs

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(
            node.name
        ):
            # Only top-level functions
            api.functions[node.name] = _format_signature(node)

    return api


def diff_apis(
    old_source: str,
    new_source: str,
    file: str = "",
) -> list[SymbolChange]:
    """Compare two versions of a Python file and return what changed.

    Parameters
    ----------
    old_source : str
        The source code of the old version of the Python module.
    new_source : str
        The source code of the new version of the Python module.
    file : str, optional
        The name of the file being compared, by default "".

    Returns
    -------
    list[SymbolChange]
        A list of changes detected between the old and new versions.
    """
    old_api = extract_public_api(old_source)
    new_api = extract_public_api(new_source)

    changes: list[SymbolChange] = []

    # Diff top-level functions
    changes.extend(_diff_signatures(old_api.functions, new_api.functions, file))

    # Diff classes
    old_classes = set(old_api.classes)
    new_classes = set(new_api.classes)

    for cls in old_classes - new_classes:
        changes.append(SymbolChange(cls, ChangeType.REMOVED, file=file))

    for cls in new_classes - old_classes:
        changes.append(SymbolChange(cls, ChangeType.ADDED, file=file))

    # Diff methods within classes that exist in both
    for cls in old_classes & new_classes:
        old_methods = {
            k.split(".")[1]: v
            for k, v in old_api.methods.items()
            if k.startswith(f"{cls}.")
        }
        new_methods = {
            k.split(".")[1]: v
            for k, v in new_api.methods.items()
            if k.startswith(f"{cls}.")
        }
        for change in _diff_signatures(old_methods, new_methods, file):
            # Prefix with class name
            change.name = f"{cls}.{change.name}"
            if change.old_signature:
                change.old_signature = f"{cls}.{change.old_signature}"
            if change.new_signature:
                change.new_signature = f"{cls}.{change.new_signature}"
            changes.append(change)

    return changes


def _diff_signatures(
    old: dict[str, str],
    new: dict[str, str],
    file: str,
) -> list[SymbolChange]:
    """Helper to diff two sets of signatures (functions or methods)."""
    changes: list[SymbolChange] = []

    removed = set(old) - set(new)
    added = set(new) - set(old)

    # Detect renames: removed + added where signatures are very similar
    matched_removed: set[str] = set()
    matched_added: set[str] = set()

    for r in removed:
        for a in added:
            old_sig = old[r]
            new_sig = new[a]
            # Same params, different name → likely rename
            old_params = old_sig[old_sig.index("(") :]
            new_params = new_sig[new_sig.index("(") :]
            if old_params == new_params:
                changes.append(
                    SymbolChange(
                        name=a,
                        change_type=ChangeType.RENAMED,
                        old_signature=r,
                        new_signature=a,
                        file=file,
                    )
                )
                matched_removed.add(r)
                matched_added.add(a)
                break

    for name in removed - matched_removed:
        changes.append(SymbolChange(name, ChangeType.REMOVED, file=file))

    for name in added - matched_added:
        changes.append(SymbolChange(name, ChangeType.ADDED, file=file))

    # Detect signature changes for functions that exist in both
    for name in set(old) & set(new):
        if old[name] != new[name]:
            changes.append(
                SymbolChange(
                    name=name,
                    change_type=ChangeType.SIGNATURE_CHANGED,
                    old_signature=old[name],
                    new_signature=new[name],
                    file=file,
                )
            )

    return changes
