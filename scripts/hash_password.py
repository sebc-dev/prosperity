"""Hash a password offline for ``INITIAL_ADMIN_PASSWORD_HASH`` (S03.3).

Reads the password from a confirmed ``getpass`` prompt (never from CLI
args or env, so it cannot leak into shell history or ``ps aux``),
computes the Argon2id hash via the same ``pwdlib`` recipe the backend
uses (``PasswordHash.recommended()``), and prints the resulting hash to
stdout. All other messages go to stderr so the stdout capture is clean
for shell interpolation.

Usage::

    python scripts/hash_password.py
    # Password: (hidden)
    # Confirm:  (hidden)
    # $argon2id$v=19$m=65536,t=3,p=4$...

    export INITIAL_ADMIN_PASSWORD_HASH="$(python scripts/hash_password.py)"

Exit codes:
    0 — hash printed to stdout
    1 — input invalid (mismatch or below 12-char floor)
    2 — refusing to read from a non-TTY stdin (would echo the password)
"""

from __future__ import annotations

import getpass
import sys

from pwdlib import PasswordHash

# Matches `backend.modules.accounts.schemas._PASSWORD_MIN_LENGTH`. Keeping
# the floor identical means an operator who generates a hash with this
# script can later authenticate via `/auth/login` without surprise.
_PASSWORD_MIN_LENGTH = 12


def main() -> int:
    # Refuse non-TTY stdin so a careless `python scripts/hash_password.py
    # < secrets.txt` doesn't silently read with echo (getpass falls back
    # to a regular `input()` with `GetPassWarning`). Forcing interactive
    # input keeps the contract "the password never lives on disk".
    if not sys.stdin.isatty():
        print(
            "Error: refusing to read password from non-TTY stdin "
            "(password would echo). Run this interactively.",
            file=sys.stderr,
        )
        return 2

    print(
        "Reading password (input hidden). "
        "It will be Argon2id-hashed locally; the plaintext never leaves this process.",
        file=sys.stderr,
    )
    pw = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm:  ")
    if pw != confirm:
        print("Error: passwords do not match.", file=sys.stderr)
        return 1
    if len(pw) < _PASSWORD_MIN_LENGTH:
        print(
            f"Error: password must be at least {_PASSWORD_MIN_LENGTH} characters "
            "(matches the SetupRequest floor).",
            file=sys.stderr,
        )
        return 1

    # `PasswordHash.recommended()` matches `auth.service._password.password_hasher()`
    # parameters; the backend's `pwdlib.verify()` at /auth/login accepts the
    # output verbatim. Constructing locally (vs. importing `auth.service._password`)
    # keeps the script free of the `backend/` package and avoids dragging the
    # `pyright`/`ruff` strict config that applies in-tree.
    hasher = PasswordHash.recommended()
    print(hasher.hash(pw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
