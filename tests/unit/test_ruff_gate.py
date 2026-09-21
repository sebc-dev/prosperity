"""`ruff check .` extended families: complexity, pytest idioms, safe fixes (S06).

Six scenarios, one per success criterion:

- SC-06a: a function whose cyclomatic complexity exceeds 10 fails on `C901`,
  the message naming the function and its measured value; the boundary
  (complexity exactly 10) stays silent.
- SC-06b: a `pytest.raises` without `match` nor a precise exception type
  fails on `PT011`; the calibration for `tests/**` never silences it.
- SC-06c: `ruff check . --fix` (no `--unsafe-fixes`) never applies a fix
  ruff itself flags `"applicability": "unsafe"` for the families added by
  this ticket — the source comes back untouched.
- SC-06d: every rule silenced for `tests/**` in `pyproject.toml` carries,
  on its own line, an inline comment; the two rules newly silenced by this
  ticket (`PT018`, `PT019`) state the extinguished-occurrence count.
- SC-06e: a rule silenced for `tests/**` (`PT018`) still fires the same way
  in `backend/` — the calibration never leaks into production.
- SC-06f: `uv run ruff check .`, run as the gate runs it, succeeds on the
  repository as committed.

All scenarios but SC-06d and SC-06f probe via stdin: `uv run ruff check
--output-format json --stdin-filename <virtual path>` on code piped through
stdin, never a fixture written to `backend/`/`tests/` on disk — a faulty
fixture on disk would itself enter the linted surface. Same external-tool
subprocess pattern as `tests/unit/test_transactions_models.py` and
`tests/unit/test_deptry_gate.py` (assert on exit code and structured
output, no `backend/` code under test).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_ruff_stdin(virtual_path: str, code: str) -> list[dict[str, Any]]:
    """Lint `code` as if it lived at `virtual_path`, without writing it to disk."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "check",
            "--output-format",
            "json",
            "--stdin-filename",
            virtual_path,
            "-",
        ],
        input=code,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def _run_ruff_fix_stdin(virtual_path: str, code: str) -> subprocess.CompletedProcess[str]:
    """Run `ruff check --fix` (default: safe fixes only) on `code` via stdin.

    Fixed source lands on stdout; remaining/unapplied diagnostics (JSON) on
    stderr — unlike the no-`--fix` path, where JSON lands on stdout.
    """
    return subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "check",
            "--fix",
            "--output-format",
            "json",
            "--stdin-filename",
            virtual_path,
            "-",
        ],
        input=code,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _mccabe_probe(*, if_count: int) -> str:
    """A flat function with `if_count` independent `if` branches (no `else`).

    Cyclomatic complexity = `if_count + 1` (one decision point per `if`,
    plus the base path) — no magic-value comparisons, no extra branches, no
    other rule from the added families triggered incidentally.
    """
    lines = ["def probe(flags: list[bool]) -> int:", "    total = 0"]
    for i in range(if_count):
        lines.append(f"    if flags[{i}]:")
        lines.append("        total += 1")
    lines.append("    return total")
    return "\n".join(lines) + "\n"


def test_SC_06a_function_over_complexity_threshold_fails_citing_function_and_value() -> None:
    # Arrange: 10 independent `if` branches => cyclomatic complexity 11 > 10.
    code = _mccabe_probe(if_count=10)

    # Act
    diagnostics = _run_ruff_stdin("backend/_probe_c901_over.py", code)

    # Assert: C901 fires, naming the function and both the measured value
    # and the configured threshold.
    c901 = [d for d in diagnostics if d["code"] == "C901"]
    assert c901, diagnostics
    assert "probe" in c901[0]["message"]
    assert "11" in c901[0]["message"]
    assert "10" in c901[0]["message"]


def test_SC_06a_function_at_complexity_threshold_stays_silent() -> None:
    # Arrange: 9 independent `if` branches => cyclomatic complexity 10 (the
    # configured max-complexity) — the boundary value itself must pass.
    code = _mccabe_probe(if_count=9)

    # Act
    diagnostics = _run_ruff_stdin("backend/_probe_c901_at.py", code)

    # Assert: no C901 (nor anything else) at exactly the threshold.
    assert diagnostics == []


def test_SC_06b_raises_without_match_or_precise_type_fails_unless_calibrated() -> None:
    # Arrange: `pytest.raises(ValueError)` with neither `match=` nor a
    # narrower exception type — the textbook PT011 case.
    code = (
        "def test_probe() -> None:\n"
        "    import pytest\n\n"
        "    with pytest.raises(ValueError):\n"
        '        raise ValueError("boom")\n'
    )

    # Act
    diagnostics = _run_ruff_stdin("tests/unit/_probe_pt011.py", code)

    # Assert: PT011 fires...
    pt011 = [d for d in diagnostics if d["code"] == "PT011"]
    assert pt011, diagnostics
    # ...precisely because the `tests/**` calibration never lists PT011
    # among the rules it explicitly silences (unlike PT018/PT019).
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    tests_ignores_block = re.search(
        r'"tests/\*\*"\s*=\s*\[(.*?)\]', pyproject_text, flags=re.DOTALL
    )
    assert tests_ignores_block is not None, pyproject_text
    assert "PT011" not in tests_ignores_block.group(1)


def test_SC_06c_unsafe_fix_from_added_families_is_never_auto_applied() -> None:
    # Arrange: a composite `assert a and b` — PT018 offers only an
    # `"applicability": "unsafe"` fix (verified below), never a safe one.
    code = "def check(a: bool, b: bool) -> None:\n    assert a and b\n"

    # Act: `--fix` without `--unsafe-fixes` (exactly what the `backend-lint`
    # autofix in `.claude/quality.json` runs).
    result = _run_ruff_fix_stdin("backend/_probe_unsafe_fix.py", code)

    # Assert: the source comes back byte-for-byte unchanged...
    assert result.stdout == code
    # ...and the diagnostic ruff still reports is the same PT018, explicitly
    # marked unsafe — proving it was seen and deliberately not applied,
    # rather than silently missed.
    remaining = json.loads(result.stderr)
    pt018 = [d for d in remaining if d["code"] == "PT018"]
    assert pt018, result.stderr
    assert pt018[0]["fix"]["applicability"] == "unsafe"


def _tests_per_file_ignores() -> list[tuple[str, str]]:
    """Parse `[tool.ruff.lint.per-file-ignores]."tests/**"` into (code, comment) pairs."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    block = re.search(r'"tests/\*\*"\s*=\s*\[(.*?)\]', pyproject_text, flags=re.DOTALL)
    assert block is not None, pyproject_text
    entries: list[tuple[str, str]] = []
    for line in block.group(1).splitlines():
        match = re.match(r'\s*"([A-Z0-9]+)",\s*#\s*(.+?)\s*$', line)
        if match:
            entries.append((match.group(1), match.group(2)))
    return entries


def test_SC_06d_every_test_only_ignore_has_an_inline_comment_with_count_and_reason() -> None:
    # Arrange/Act: read the calibration as committed.
    entries = _tests_per_file_ignores()

    # Assert: every silenced rule for `tests/**` carries a non-empty inline
    # reason on its own line (the general contract SC-06d states)...
    codes = {code for code, _comment in entries}
    assert {"PLR2004", "PT018", "PT019"} <= codes, entries
    for code, comment in entries:
        assert comment, f"{code} has no inline comment"

    # ...and the two rules this ticket newly silences, both extinguished
    # because of their measured volume in `tests/**`, state that count
    # (the pattern PLR2004 already used loosely, made precise here).
    by_code = dict(entries)
    for volumetric_code in ("PT018", "PT019"):
        comment = by_code[volumetric_code]
        assert re.match(r"\d+ remontées", comment), (volumetric_code, comment)


def test_SC_06e_rule_calibrated_off_in_tests_still_fires_in_backend() -> None:
    # Arrange: the exact same composite-assertion snippet, PT018's target.
    code = "def test_probe(a: bool, b: bool) -> None:\n    assert a and b\n"

    # Act: once under `tests/**` (calibrated off), once under `backend/`
    # (never touched by the `tests/**` calibration).
    tests_diagnostics = _run_ruff_stdin("tests/unit/_probe_pt018.py", code)
    backend_diagnostics = _run_ruff_stdin("backend/_probe_pt018.py", code)

    # Assert: silenced in tests/, still remonté in backend/ — the
    # calibration never touches production.
    assert not any(d["code"] == "PT018" for d in tests_diagnostics), tests_diagnostics
    backend_pt018 = [d for d in backend_diagnostics if d["code"] == "PT018"]
    assert backend_pt018, backend_diagnostics


def test_SC_06f_ruff_check_succeeds_on_the_repository_baseline() -> None:
    # Arrange: no fixture needed — the repository itself, as committed on
    # this branch, is the subject under test (same shape as the
    # `backend-lint` blocking check in `.claude/quality.json`).

    # Act
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert: the gate is green on the base — no backlog on any family,
    # added or pre-existing.
    assert result.returncode == 0, result.stdout + result.stderr
