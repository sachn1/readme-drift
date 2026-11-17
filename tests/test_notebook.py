"""Execute every code cell of the demo notebook so it cannot silently break."""

import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "demo.ipynb"


def test_demo_notebook_runs_top_to_bottom(monkeypatch):
    """All code cells run in order, from the notebooks directory, without error."""
    monkeypatch.chdir(NOTEBOOK.parent)
    monkeypatch.setattr(sys, "path", list(sys.path))
    cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
    namespace: dict = {"__name__": "__notebook__"}
    for index, cell in enumerate(cells):
        if cell["cell_type"] != "code":
            continue
        code = "".join(cell["source"])
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(code, f"demo.ipynb cell {index}", "exec"), namespace)
        except Exception as exc:
            first_line = code.strip().splitlines()[0] if code.strip() else ""
            raise AssertionError(
                f"notebook cell {index} failed ({first_line!r}): {exc!r}"
            ) from exc


def test_demo_notebook_documents_the_verify_flag():
    """The notebook has a section on --verify and no removed flag syntax."""
    text = NOTEBOOK.read_text(encoding="utf-8")
    assert "10 · Verifying README commands" in text
    assert "--flag=true/false" not in text
    assert "argparse" not in text
