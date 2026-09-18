"""`deptry` gate: declared and imported Python dependencies coincide (S07).

Three scenarios, one per success criterion:

- SC-07a: a dependency declared in `pyproject.toml` but never imported anywhere
  makes `deptry` fail and name the package (`DEP002`).
- SC-07b: a module importing a package absent from `pyproject.toml` (direct or
  transitive) makes `deptry` fail and name the module/import (`DEP001`/`DEP003`).
- SC-07c: on the actual repository, where every declared dependency is imported
  and every import is declared, `deptry` succeeds — the state of the base.

SC-07a and SC-07b build a throwaway project under `tmp_path`: a minimal
`pyproject.toml` plus a tiny package, scanned via `uv run deptry <root>
--config <root>/pyproject.toml --json-output <file>`. `--config` pins the
dependency declarations to the synthetic project instead of the repo's own
`pyproject.toml` (deptry would otherwise resolve config relative to `uv run`'s
cwd, not the scanned root). Same subprocess pattern as
`tests/unit/test_transactions_models.py` (external tool, assert on exit code
and structured output — no code of `backend/` involved).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_deptry(root: Path, json_output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "deptry",
            str(root),
            "--config",
            str(root / "pyproject.toml"),
            "--json-output",
            str(json_output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_report(json_output: Path) -> list[dict[str, Any]]:
    return json.loads(json_output.read_text())


def test_SC_07a_declared_but_never_imported_package_fails_naming_it(tmp_path: Path) -> None:
    # Arrange: a project declaring "requests" but importing nothing from it.
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "probe-dep002"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["requests>=2.0"]

[tool.uv]
package = false
""".strip()
        + "\n"
    )
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "__init__.py").write_text("")
    (backend / "app.py").write_text("def run() -> None:\n    return None\n")
    json_output = tmp_path / "report.json"

    # Act
    result = _run_deptry(tmp_path, json_output)

    # Assert: failure, and the unused dependency is named as DEP002.
    assert result.returncode != 0, result.stdout + result.stderr
    report = _load_report(json_output)
    dep002_modules = {entry["module"] for entry in report if entry["error"]["code"] == "DEP002"}
    assert "requests" in dep002_modules, report


def test_SC_07b_import_of_undeclared_package_fails_naming_module_and_import(
    tmp_path: Path,
) -> None:
    # Arrange: a project declaring no dependencies, whose only module imports
    # "numpy" — neither declared nor installed (direct or transitive).
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "probe-dep001"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []

[tool.uv]
package = false
""".strip()
        + "\n"
    )
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "__init__.py").write_text("")
    (backend / "app.py").write_text("import numpy\n\n\ndef run() -> None:\n    numpy.array([1])\n")
    json_output = tmp_path / "report.json"

    # Act
    result = _run_deptry(tmp_path, json_output)

    # Assert: failure, naming both the undeclared import ("numpy") and the
    # module that performs it (DEP001: missing entirely; DEP003: declared as
    # transitive-only — either is an acceptable proof of the gate).
    assert result.returncode != 0, result.stdout + result.stderr
    report = _load_report(json_output)
    offending = [
        entry
        for entry in report
        if entry["error"]["code"] in {"DEP001", "DEP003"} and entry["module"] == "numpy"
    ]
    assert offending, report
    assert offending[0]["location"]["file"].endswith("app.py"), offending[0]


def test_SC_07c_repository_baseline_passes(tmp_path: Path) -> None:
    # Arrange: no fixture needed — the repository itself, as committed, is the
    # subject under test (every declared dependency imported, every import
    # declared).
    json_output = tmp_path / "report.json"

    # Act
    result = subprocess.run(
        ["uv", "run", "deptry", ".", "--json-output", str(json_output)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0, result.stdout + result.stderr
    assert _load_report(json_output) == []
