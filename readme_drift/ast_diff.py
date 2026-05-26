"""AST-based diffing to extract changed public symbols between two code versions."""

import ast

from .models import ChangeType, PublicAPI, SymbolChange


def _is_public(name: str) -> bool:
    """Determine if a name is public (does not start with an underscore)."""
    return not name.startswith("_")


def _positional_args_with_defaults(
    arg_list: list[ast.arg],
    offset: int,
    num_all: int,
    defaults: list[ast.expr],
) -> list[str]:
    """Format a slice of positional args, resolving the shared defaults array."""
    num_defaults = len(defaults)
    result = []
    for i, arg in enumerate(arg_list):
        if arg.arg in ("self", "cls"):
            continue
        default_index = (offset + i) - (num_all - num_defaults)

        # default_index >= 0 means this arg has a default value in the defaults array
        if default_index >= 0:
            result.append(f"{arg.arg}={ast.unparse(defaults[default_index])}")
        else:
            result.append(arg.arg)
    return result


def _kwonly_args(
    kwonlyargs: list[ast.arg],
    kw_defaults: list[ast.expr | None],
) -> list[str]:
    """Format keyword-only args with their optional defaults."""
    result = []
    for arg, default in zip(kwonlyargs, kw_defaults):
        if default is not None:
            result.append(f"{arg.arg}={ast.unparse(default)}")
        else:
            result.append(arg.arg)
    return result


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Format a function/method signature as a readable string.

    ast.unparse is intentionally avoided: it retains self/cls and type
    annotations, which only affects report readability — the signature
    string is never used for detection, only for display in the output.
    """
    func_args = node.args
    num_all = len(func_args.posonlyargs) + len(func_args.args)

    posonly = _positional_args_with_defaults(
        func_args.posonlyargs, 0, num_all, func_args.defaults
    )

    regular = _positional_args_with_defaults(
        func_args.args, len(func_args.posonlyargs), num_all, func_args.defaults
    )

    parts = [*posonly]
    if posonly:
        parts.append("/")
    parts.extend(regular)

    if func_args.vararg:
        parts.append(f"*{func_args.vararg.arg}")
    elif func_args.kwonlyargs:
        parts.append("*")

    parts.extend(_kwonly_args(func_args.kwonlyargs, func_args.kw_defaults))

    if func_args.kwarg:
        parts.append(f"**{func_args.kwarg.arg}")

    return f"{node.name}({', '.join(parts)})"


def extract_public_api(source: str, *, include_private: bool = False) -> PublicAPI:
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

    is_visible = (lambda _: True) if include_private else _is_public

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and is_visible(node.name):
            method_sigs: set[str] = set()
            for item in node.body:
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and is_visible(item.name):
                    sig = _format_signature(item)
                    method_sigs.add(sig)
                    api.methods[f"{node.name}.{item.name}"] = sig
            api.classes[node.name] = method_sigs

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_visible(
            node.name
        ):
            # Only top-level functions
            api.functions[node.name] = _format_signature(node)

    return api


def diff_apis(
    old_source: str,
    new_source: str,
    file: str = "",
    *,
    include_private: bool = False,
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
    include_private : bool, optional
        If True, include private (underscore-prefixed) symbols, by default False.

    Returns
    -------
    list[SymbolChange]
        A list of changes detected between the old and new versions.
    """
    old_api = extract_public_api(old_source, include_private=include_private)
    new_api = extract_public_api(new_source, include_private=include_private)

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

    for name in set(old) - set(new):
        changes.append(SymbolChange(name, ChangeType.REMOVED, file=file))

    for name in set(new) - set(old):
        changes.append(SymbolChange(name, ChangeType.ADDED, file=file))

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
