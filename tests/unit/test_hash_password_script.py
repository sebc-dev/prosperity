"""Unit tests for `scripts/hash_password.py` (S03.3).

The script is path-loaded (no `__init__.py` in `scripts/`) so it can
stay out of `backend/` strictness. Tests load it via `importlib` and
monkeypatch `getpass` / `sys.stdin.isatty()` to drive the interactive
prompt deterministically.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from pwdlib import PasswordHash

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hash_password.py"


@pytest.fixture
def script_module() -> Iterator[ModuleType]:
    """Load `scripts/hash_password.py` as a module without touching `sys.path`.

    The script lives outside the `backend` package; `importlib`'s
    spec-from-file-location lets the tests poke at `main()`, the
    in-module `getpass` reference, and `sys.stdin` without mutating
    global state across the test session.
    """
    spec = importlib.util.spec_from_file_location("hash_password_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("hash_password_under_test", None)


def _force_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `sys.stdin.isatty()` return True so the TTY guard doesn't trip."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _stub_getpass(monkeypatch: pytest.MonkeyPatch, module: ModuleType, *answers: str) -> None:
    """Replace `getpass.getpass` inside the script's namespace.

    Patching the script's own `getpass` import (not `getpass.getpass`
    globally) keeps the patch surface small — pytest's own `getpass`
    calls (none today, but defensive) wouldn't be affected.
    """
    answers_iter = iter(answers)

    def _fake(_prompt: str = "") -> str:
        try:
            return next(answers_iter)
        except StopIteration as exc:
            raise AssertionError("getpass called more times than expected") from exc

    monkeypatch.setattr(module.getpass, "getpass", _fake)


def test_main_prints_valid_argon2id_hash_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Round-trip: hash printed to stdout verifies the plaintext via `pwdlib`."""
    _force_tty(monkeypatch)
    _stub_getpass(monkeypatch, script_module, "correct-horse-battery", "correct-horse-battery")

    rc = script_module.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out.startswith("$argon2id$")
    # Single line on stdout — important for `INITIAL_ADMIN_PASSWORD_HASH="$(...)"`.
    assert captured.out.count("\n") == 1
    # All operator-facing messages go to stderr — stdout is data only.
    assert "hidden" in captured.err

    # Round-trip via the same recipe the backend uses at /auth/login.
    assert PasswordHash.recommended().verify("correct-horse-battery", captured.out.strip())


def test_main_rejects_mismatched_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _force_tty(monkeypatch)
    _stub_getpass(monkeypatch, script_module, "first-password-123", "different-password-456")

    rc = script_module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "do not match" in captured.err
    # Stdout must be empty so a careless `$(...)` capture in shell
    # doesn't end up exporting a partial / unintended value.
    assert captured.out == ""


def test_main_rejects_password_below_twelve_chars(
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same floor as `SetupRequest.password.min_length` — no surprise at `/auth/login`."""
    _force_tty(monkeypatch)
    _stub_getpass(monkeypatch, script_module, "short", "short")

    rc = script_module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "12 characters" in captured.err
    assert captured.out == ""


def test_main_refuses_non_tty_stdin(
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`< secrets.txt` is rejected with exit code 2 (would echo otherwise)."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    rc = script_module.main()
    captured = capsys.readouterr()

    assert rc == 2
    assert "non-TTY" in captured.err
    assert captured.out == ""
