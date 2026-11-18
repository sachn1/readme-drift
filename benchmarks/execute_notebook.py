"""Execute analysis.ipynb and store its outputs, so the committed notebook doubles as the report."""

import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "analysis.ipynb"


def _run(cells: list[dict]) -> int:
    """Run every code cell in order, filling in its outputs; return the failure count."""
    sys.path.insert(0, str(HERE))
    import triage

    namespace: dict = {"__name__": "__notebook__"}
    current: list[list[dict]] = [[]]

    def show(text: str) -> None:
        """Record Markdown shown by the running cell as a rich notebook output."""
        lines = text.splitlines(keepends=True)
        current[0].append(
            {
                "output_type": "display_data",
                "data": {"text/markdown": lines, "text/plain": lines},
                "metadata": {},
            }
        )

    triage.show = show
    failures = 0
    for index, cell in enumerate(cells):
        if cell["cell_type"] != "code":
            continue
        outputs: list[dict] = []
        current[0] = outputs
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                exec(
                    compile(
                        "".join(cell["source"]), f"analysis.ipynb cell {index}", "exec"
                    ),
                    namespace,
                )
        except Exception as exc:  # noqa: BLE001 - report every failing cell
            failures += 1
            outputs.append(
                {
                    "output_type": "error",
                    "ename": type(exc).__name__,
                    "evalue": str(exc),
                    "traceback": [],
                }
            )
        if buffer.getvalue():
            outputs.insert(
                0,
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": buffer.getvalue().splitlines(keepends=True),
                },
            )
        cell["outputs"] = outputs
        cell["execution_count"] = index
    return failures


def main() -> None:
    """Run the notebook against the current results and rewrite it with outputs.

    Returns
    -------
    None
        Exits non-zero if any cell failed.
    """
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    failures = _run(notebook["cells"])
    NOTEBOOK.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"executed {NOTEBOOK.name}: {failures} failing cell(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
