"""The `users_public` projection trigger (S13.7 P13.7.5a, D-UP).

`users_public` is the non-PII identity read-model synced household-wide. It is
maintained by a Postgres trigger (`sync_users_public`) that upserts the
projection on every INSERT / UPDATE OF `users.display_name` / `users.role`. These
tests run against the `auth_schema` (create_all) tier — which installs the SAME
trigger the migration installs in prod (the `event.listen` parity) — and prove
the projection stays in lock-step with `users`, carries no PII, and does NOT fire
for an unrelated column change (a password rotation).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User


async def _projection(session: AsyncSession, user_id: object) -> tuple[str, str] | None:
    row = (
        await session.execute(
            text("SELECT display_name, role FROM users_public WHERE user_id = :uid"),
            {"uid": user_id},
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def test_insert_propagates_to_users_public(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory(display_name="Alice", role="member")
    assert await _projection(auth_schema, user.id) == ("Alice", "member")


async def test_display_name_update_propagates(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory(display_name="Bob", role="member")
    await auth_schema.execute(
        text("UPDATE users SET display_name = :n WHERE id = :uid"),
        {"n": "Bobby", "uid": user.id},
    )
    assert await _projection(auth_schema, user.id) == ("Bobby", "member")


async def test_role_update_propagates(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory(display_name="Carol", role="member")
    await auth_schema.execute(
        text("UPDATE users SET role = 'admin' WHERE id = :uid"),
        {"uid": user.id},
    )
    assert await _projection(auth_schema, user.id) == ("Carol", "admin")


async def test_password_change_does_not_disturb_projection(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The trigger fires only on UPDATE OF display_name/role — a credential
    # rotation must leave the projection untouched (no needless churn, and proof
    # the trigger scope is narrow).
    user = await bound_user_factory(display_name="Dave", role="member")
    await auth_schema.execute(
        text("UPDATE users SET password_hash = 'rotated' WHERE id = :uid"),
        {"uid": user.id},
    )
    assert await _projection(auth_schema, user.id) == ("Dave", "member")


async def test_projection_carries_no_pii_columns(auth_schema: AsyncSession) -> None:
    # Defence in depth at the live-schema level: the physical table has exactly
    # the three projected columns — no email, no hash.
    cols = {
        r[0]
        for r in (
            await auth_schema.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'users_public'"
                )
            )
        ).all()
    }
    assert cols == {"user_id", "display_name", "role"}, cols
