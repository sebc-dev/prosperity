"""Dispatcher du write upload handler PowerSync (ADR 0014).

`process_batch` parcourt `batch.mutations` DANS L'ORDRE DU TABLEAU (ordering
préservé, ADR 0014 ; pas de parallélisation) et matérialise la séquence par
mutation. S13.3 pose les étapes 0-2 : routage (sous-handler de `table` ou
`unknown_table`) → étape 1 auth/RBAC (P13.3.2) → étape 2 idempotence (P13.3.3).
Les étapes 3-10 (validation, write, matérialisation, events, commit, append log,
ack) vivent dans les sous-handlers (S13.4) et la frontière transactionnelle
(S13.6) ; ici les handlers sont une COUTURE injectable (mockés en test).

Registres CENTRAUX (ADR 0014 : auditables d'un seul endroit) :
- HANDLERS    : `table -> Handler` (vide en S13.3, peuplé par S13.4).
- PERMISSION_CHECKS : `(table, op) -> PermissionCheck` (étape 1).

⚠️ Ordre de déclaration : `from __future__ import annotations` stringifie les
*annotations*, mais les *valeurs par défaut* (`handlers=HANDLERS`,
`permission_checks=PERMISSION_CHECKS`) sont évaluées AU RUNTIME à la définition
de `process_batch` → les registres et leurs fns de check sont déclarés AU-DESSUS
de la fonction (sinon `NameError`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import account_is_accessible
from backend.modules.auth.public import User
from backend.modules.sync.schemas import (
    BatchUpload,
    Mutation,
    MutationOp,
    WriteError,
    WriteResult,
)
from backend.modules.sync.service.idempotency import already_processed


class Handler(Protocol):
    """Sous-handler par table (S13.4). Reçoit la session (UoW de l'appelant),
    l'utilisateur authentifié et la mutation ; renvoie le `WriteResult` (ack)."""

    async def __call__(
        self, session: AsyncSession, user: User, mutation: Mutation
    ) -> WriteResult: ...


class IdempotencyCheck(Protocol):
    """Lookup d'idempotence (étape 2). Défaut = `already_processed` (lecture scopée
    user de `sync_request_log`). Injectable comme `handlers`/`permission_checks` :
    les tests de ROUTAGE unitaires stubent un `→ False` pour rester DB-free sans
    mocker la session SQLA (anti-pattern repo) ; l'intégration garde le défaut réel."""

    async def __call__(
        self, session: AsyncSession, *, user_id: UUID, client_request_id: UUID
    ) -> bool: ...


# Registre CENTRAL de routage : `table -> Handler`. VIDE en S13.3 — la machine
# existe, les vrais handlers sont enregistrés en S13.4. Clé absente ⇒
# `unknown_table` (la suite du batch continue). Les tests INJECTENT un registre
# mocké via le paramètre `handlers` de `process_batch` (couture explicite ≻
# monkeypatch) pour prouver le routage sans dépendre des handlers réels.
HANDLERS: dict[str, Handler] = {}  # peuplé en S13.4


# ── Étape 1 : auth / RBAC (P13.3.2) ──────────────────────────────────────────
# Le lookup `(table, op) -> permission_check_fn` est CENTRALISÉ ici (note issue +
# ADR 0014 : auditable d'un seul endroit), pas dispersé dans les handlers. S13.4
# ÉTEND ce même registre central (update/delete + autres tables) — il ne le
# disperse pas.

PermissionCheck = Callable[[AsyncSession, User, Mutation], Awaitable[bool]]


def _payload_uuid(value: object) -> UUID | None:
    """Coercition best-effort d'une valeur de payload en `UUID`, AVANT la
    validation Pydantic par-table (ordre ADR 0014 : auth court avant validation).
    Renvoie `None` (→ fail-closed) pour `None`, un type non-scalaire
    (`list`/`dict`) ou un UUID mal formé — jamais d'exception qui remonte.

    `bool` est rejeté explicitement : `UUID(str(True))` lèverait, mais on ne veut
    pas dépendre de ce hasard — un booléen n'est pas un identifiant de compte.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _referenced_account_ids(payload: dict[str, object]) -> list[UUID] | None:
    """TOUS les comptes qu'une mutation `transactions/insert` touche : le compte
    racine ET chaque `split.account_id` (un transfert en couvre ≥ 2,
    `transactions.domain.is_transfer`). Best-effort AVANT validation Pydantic,
    agnostique de la décomposition wire finale (la forme par-table est S13.4).

    Fail-closed (`None`) si AUCUN compte exploitable OU si une référence présente
    est malformée / d'une structure douteuse — on ne devine pas, on refuse.
    """
    ids: list[UUID] = []
    if "account_id" in payload:  # compte racine
        root = _payload_uuid(payload["account_id"])
        if root is None:
            return None  # présent mais malformé → deny
        ids.append(root)
    splits = payload.get("splits")
    if isinstance(splits, list):  # ventilation / transfert
        for split in cast("list[object]", splits):
            if not isinstance(split, dict):
                return None  # structure douteuse → deny
            split_map = cast("dict[str, object]", split)
            if "account_id" not in split_map:
                return None
            sid = _payload_uuid(split_map["account_id"])
            if sid is None:
                return None
            ids.append(sid)
    elif splits is not None:
        return None  # `splits` présent mais pas une liste → deny
    return ids or None  # aucun compte → fail-closed


async def _check_create_transaction(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Étape 1 pour `insert` sur `transactions` : TOUS les comptes touchés
    (racine + chaque split — un transfert en couvre ≥ 2) doivent être accessibles
    (owner ∪ live-member ; admin NON exempté — `account_is_accessible` est
    role-blind). Un seul compte inaccessible → deny (sinon on sous-autoriserait un
    transfert glissant une jambe vers un compte d'autrui — finding Sécu Majeur)."""
    account_ids = _referenced_account_ids(mutation.payload)
    if not account_ids:
        return False  # fail-closed
    for account_id in account_ids:
        if not await account_is_accessible(session, account_id=account_id, user_id=user.id):
            return False  # un seul inaccessible → deny
    return True


# Registre CENTRAL des checks d'auth (étape 1). S13.4 ÉTEND : update/delete (compte
# du row via `transactions.public.get_transaction`) + autres tables (`accounts`,
# `budget`, `settlements`, …) et — si décomposition wire plate — un check par
# `(transaction_splits, insert)`, garanti exhaustif par le test de parité S13.4.
PERMISSION_CHECKS: dict[tuple[str, MutationOp], PermissionCheck] = {
    ("transactions", "insert"): _check_create_transaction,
}


_UNKNOWN_TABLE = "unknown_table"  # vocabulaire ADR 0014 (resserré Literal en S13.6/D8)
_AUTH_DENIED = "auth_denied"  # vocabulaire ADR 0014


async def process_batch(  # noqa: PLR0913 — 3 coutures de test keyword-only injectables
    session: AsyncSession,
    user: User,
    batch: BatchUpload,
    *,
    handlers: Mapping[str, Handler] = HANDLERS,
    permission_checks: Mapping[tuple[str, MutationOp], PermissionCheck] = PERMISSION_CHECKS,
    is_processed: IdempotencyCheck = already_processed,
) -> list[WriteResult]:
    """Route chaque mutation vers le sous-handler de sa `table`, dans l'ordre du
    tableau (séquentiel, pas de parallélisation — ADR 0014). Par mutation :

    0. routage : table inconnue → `unknown_table` (la suite du batch continue) ;
    1. auth/RBAC : `(table, op)` non mappé OU check `False` → `auth_denied`
       (fail-closed — un handler routable sans politique d'auth est une lacune de
       config, pas un laissez-passer) ;
    2. idempotence : `client_request_id` déjà dans `sync_request_log` (scopé user)
       → ack `success=True` SANS appeler le handler (replay d'un write déjà commité) ;
    puis délégation au handler (mocké S13.3).

    La session (UoW de l'appelant, ADR 0015) est threadée aux checks et au
    handler ; AUCUN `commit()` ici (la frontière par-mutation est S13.6).
    `handlers` / `permission_checks` / `is_processed` injectables = couture de test
    + point d'enregistrement S13.4 (défaut = registres / lookup module).
    """
    results: list[WriteResult] = []
    for mutation in batch.mutations:  # ordre préservé, séquentiel
        handler = handlers.get(mutation.table)
        if handler is None:
            results.append(
                WriteResult(
                    client_request_id=mutation.client_request_id,
                    success=False,
                    error=WriteError(code=_UNKNOWN_TABLE, message="Unknown table."),
                )
            )
            continue  # la suite du batch continue (ADR 0014)
        check = permission_checks.get((mutation.table, mutation.op))
        if check is None or not await check(session, user, mutation):  # fail-closed
            results.append(
                WriteResult(
                    client_request_id=mutation.client_request_id,
                    success=False,
                    error=WriteError(code=_AUTH_DENIED, message="Not authorized."),
                )
            )
            continue
        if await is_processed(
            session, user_id=user.id, client_request_id=mutation.client_request_id
        ):
            # Replay d'une mutation déjà commitée (étape 9, S13.6) : ack SANS
            # ré-écrire (handler NON appelé) — idempotence stricte, scopée user.
            results.append(WriteResult(client_request_id=mutation.client_request_id, success=True))
            continue
        results.append(await handler(session, user, mutation))
    return results
