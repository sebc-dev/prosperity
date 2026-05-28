"""Shared Argon2id `PasswordHash` factory for the auth module.

`PasswordHash.recommended()` allocates Argon2id parameters (memory_cost,
time_cost, parallelism) that take 50-200ms on first construction. The
factory is module-private and `@cache`-d so the entire process shares
**one** instance — both the transport (`auth/transports/http.py`) and
the user-creation service (`auth/service/users.py`) call into the same
hasher, so a future Argon2id parameter tune is a one-site change and
the cache hit rate stays at 100%.

Marked underscore-private (`_password.py`) because no cross-module
caller has any reason to construct a `PasswordHash` itself — they go
through `create_user` / route handlers.
"""

from __future__ import annotations

from functools import cache

from pwdlib import PasswordHash


@cache
def password_hasher() -> PasswordHash:
    return PasswordHash.recommended()
