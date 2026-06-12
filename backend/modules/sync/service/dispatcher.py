"""Dispatcher du write upload handler PowerSync (ADR 0014).

`process_batch` parcourt `batch.mutations` DANS L'ORDRE DU TABLEAU (ordering
préservé, ADR 0014 ; pas de parallélisation) et matérialise la séquence par
mutation. S13.3 pose les étapes 0-2 : routage (sous-handler de `table` ou
`unknown_table`) → étape 1 auth/RBAC (P13.3.2) → étape 2 idempotence (P13.3.3).
Les étapes 3-7 (validation, write, matérialisation, events) vivent dans les
sous-handlers (S13.4, flush-only) ; la FRONTIÈRE TRANSACTIONNELLE par mutation —
étape 8 `commit`, étape 9 append `sync_request_log`, étape 10 ack — est posée ICI
(S13.6) autour de chaque handler. Les handlers restent une COUTURE injectable
(mockés en test).

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

from backend.modules.accounts.public import accessible_account_ids, account_is_accessible
from backend.modules.auth.public import User, user_is_active_member
from backend.modules.sync.handlers import accounts as h_acc
from backend.modules.sync.handlers import budget as h_budget
from backend.modules.sync.handlers import reconciliations as h_rec
from backend.modules.sync.handlers import settlements as h_settle
from backend.modules.sync.handlers import share_requests as h_sr
from backend.modules.sync.handlers import transactions as h_tx
from backend.modules.sync.schemas import (
    BatchUpload,
    Mutation,
    MutationOp,
    WriteError,
    WriteErrorCode,
    WriteResult,
)
from backend.modules.sync.service.errors import to_write_error
from backend.modules.sync.service.idempotency import already_processed, record_processed
from backend.modules.transactions.public import get_transaction


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


# Registre CENTRAL de routage : `table -> Handler`. PEUPLÉ en S13.4 (la machine
# vient de S13.3). Clé absente ⇒ `unknown_table` (la suite du batch continue). Les
# tests de ROUTAGE unitaires INJECTENT un registre mocké via le paramètre `handlers`
# de `process_batch` (couture explicite ≻ monkeypatch) ; l'intégration garde le défaut
# réel. `splits` partage le handler de `transactions` (le split est interne à
# l'aggregate, D-C) ; `categories`/`budgets` partagent le module `budget` (delta D5).
HANDLERS: dict[str, Handler] = {
    "transactions": h_tx.handle_transaction,
    "splits": h_tx.handle_split,
    "accounts": h_acc.handle_account,
    "categories": h_budget.handle_category,
    "budgets": h_budget.handle_budget,
    "settlements": h_settle.handle_settlement,
    "share_requests": h_sr.handle_share_request,
    "reconciliations": h_rec.handle_reconciliation,
}

# Source de vérité DÉCLARATIVE des ops gérées par chaque handler — rend le verrou de
# parité (`tests/unit/test_sync_registry_parity.py`) décidable dans LES DEUX SENS
# (toute op gérée a une politique d'auth ; tout check porte sur une op gérée). Le
# handler dispatche sur `mutation.op` ; `SUPPORTED_OPS[table]` déclare l'ensemble
# couvert. `reconciliations` est le placeholder V1 (D-H) : check « membre » qui passe,
# puis `not_implemented_yet`.
SUPPORTED_OPS: dict[str, frozenset[MutationOp]] = {
    "transactions": frozenset({"insert", "update", "delete"}),
    "splits": frozenset({"insert", "delete"}),
    "accounts": frozenset({"insert", "update", "delete"}),
    "categories": frozenset({"insert", "update", "delete"}),
    "budgets": frozenset({"insert", "update", "delete"}),
    "settlements": frozenset({"insert"}),
    "share_requests": frozenset({"insert", "delete"}),
    "reconciliations": frozenset({"insert", "update", "delete"}),
}


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
    racine ET chaque `split.account_id` embarqué. Best-effort AVANT validation
    Pydantic, fail-closed (`None`) si AUCUN compte exploitable OU si une référence
    présente est malformée / d'une structure douteuse — on ne devine pas, on refuse.

    ⚠️ Sous la décomposition wire PLATE de S13.4 (D-A), un `transactions/insert`
    ne porte plus de `splits` embarqué (`TransactionInsertPayload` est
    `extra="forbid"`) : la branche `splits` ci-dessous est donc INERTE en pratique,
    conservée en défense-en-profondeur. La garantie « pas de jambe glissée vers un
    compte d'autrui » vit désormais dans `_check_mutate_split` au `splits/insert`
    (D-N). Élagage possible quand le contrat wire est figé (S13.6).
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
    (owner ∪ live-member ; admin NON exempté — `accessible_account_ids` est
    role-blind). Un seul compte inaccessible → deny (sinon on sous-autoriserait un
    transfert glissant une jambe vers un compte d'autrui — finding Sécu Majeur).

    L'ensemble accessible est résolu en UN SEUL SELECT (`accessible_account_ids`),
    puis chaque compte référencé est testé par appartenance ensembliste — vs N
    requêtes `account_is_accessible` pour un transfert à N jambes (même prédicat
    `_accessible`, donc équivalent : `aid ∈ accessible_account_ids(user)` ⟺
    `account_is_accessible(aid, user)`)."""
    account_ids = _referenced_account_ids(mutation.payload)
    if account_ids is None:
        return False  # fail-closed (aucun compte exploitable / payload douteux)
    accessible = await accessible_account_ids(session, user_id=user.id)
    return all(account_id in accessible for account_id in account_ids)


async def _check_mutate_transaction(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Étape 1 pour `update`/`delete` sur `transactions` : le compte du row doit être
    accessible. Fail-closed via `_payload_uuid(p.get("id"))` — JAMAIS `p["id"]` (un
    `KeyError`/`ValueError` qui remonterait casserait le batch, discipline S13.3)."""
    tx_id = _payload_uuid(mutation.payload.get("id"))
    if tx_id is None:
        return False
    txn = await get_transaction(session, tx_id=tx_id)
    return txn is not None and await account_is_accessible(
        session, account_id=txn.account_id, user_id=user.id
    )


async def _check_mutate_split(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Étape 1 pour `insert`/`delete` sur `splits` (D-D, D-F). Le compte parent (via
    `payload["transaction_id"]`) doit être accessible ; pour un `insert`, le compte de
    la JAMBE (`payload["account_id"]`, qui peut viser un autre compte sur un transfert)
    doit l'être aussi — c'est ici que migre la garantie « pas de jambe glissée vers un
    compte d'autrui » sous la décomposition plate (D-N). Tout fail-closed."""
    payload = mutation.payload
    tx_id = _payload_uuid(payload.get("transaction_id"))
    if tx_id is None:
        return False
    txn = await get_transaction(session, tx_id=tx_id)
    if txn is None or not await account_is_accessible(
        session, account_id=txn.account_id, user_id=user.id
    ):
        return False
    if "account_id" in payload:  # insert : la jambe peut viser un autre compte
        leg = _payload_uuid(payload.get("account_id"))
        return leg is not None and await account_is_accessible(
            session, account_id=leg, user_id=user.id
        )
    return True


def _member_user_ids(payload: dict[str, object]) -> list[UUID] | None:
    """Les `user_id` des membres d'un `accounts/insert` commun, best-effort fail-closed
    (`None` si `members` absent/vide/malformé). Sert le contrôle d'appartenance D-M."""
    members = payload.get("members")
    if not isinstance(members, list) or not members:
        return None
    ids: list[UUID] = []
    for member in cast("list[object]", members):
        if not isinstance(member, dict):
            return None
        uid = _payload_uuid(cast("dict[str, object]", member).get("user_id"))
        if uid is None:
            return None
        ids.append(uid)
    return ids


async def _check_create_account(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Étape 1 pour `accounts/insert`. Commun (présence de `members`, D-M) : le caller
    DOIT figurer parmi les membres ET chaque membre doit être un membre actif du foyer
    — sinon un membre créerait un compte commun entre tiers, sans lui, avec des ratios
    arbitraires (`create_shared` ne valide QUE la forme / Σ, pas l'appartenance).
    Personnel : `user_is_active_member(user.id)` (owner forcé `user.id` par le handler)."""
    payload = mutation.payload
    if "members" in payload:  # compte commun (D-M)
        member_ids = _member_user_ids(payload)
        if member_ids is None or user.id not in member_ids:
            return False  # fail-closed / caller exclu
        for uid in member_ids:
            if not await user_is_active_member(session, user_id=uid):
                return False
        return True
    return await user_is_active_member(session, user_id=user.id)


async def _check_mutate_account(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Étape 1 pour `accounts/update`/`delete` (rename/archive) : compte accessible."""
    account_id = _payload_uuid(mutation.payload.get("id"))
    return account_id is not None and await account_is_accessible(
        session, account_id=account_id, user_id=user.id
    )


async def _check_active_member(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    """Gate « membre actif du foyer » (D-F) : suffisant quand le SERVICE porte une auth
    fine 404-first (budgets via `get_visible_budget`, settlements/share_requests
    404-first, `by_user_id` forcé) ou est household-global (catégories, singleton V1).

    ⚠️ Dépendance singleton mono-foyer V1 pour `categories` (le service ne prend ni
    `user_id` ni filtre foyer) : un futur multi-foyer devra scoper par `household_id`."""
    return await user_is_active_member(session, user_id=user.id)


# Registre CENTRAL des checks d'auth (étape 1) — ÉTENDU en S13.4. Source unique
# auditable (ADR 0014). `_check_create_transaction` (S13.3) reste branché sur
# `("transactions","insert")` (D-N). Les ops d'une table connue SANS entrée ici sont
# fail-closed (`auth_denied`) → leur handler n'est jamais atteint (D-G). Le verrou de
# parité (`SUPPORTED_OPS`) garantit l'exhaustivité dans les deux sens.
PERMISSION_CHECKS: dict[tuple[str, MutationOp], PermissionCheck] = {
    ("transactions", "insert"): _check_create_transaction,
    ("transactions", "update"): _check_mutate_transaction,
    ("transactions", "delete"): _check_mutate_transaction,
    ("splits", "insert"): _check_mutate_split,
    ("splits", "delete"): _check_mutate_split,
    ("accounts", "insert"): _check_create_account,
    ("accounts", "update"): _check_mutate_account,
    ("accounts", "delete"): _check_mutate_account,
    ("categories", "insert"): _check_active_member,
    ("categories", "update"): _check_active_member,
    ("categories", "delete"): _check_active_member,
    ("budgets", "insert"): _check_active_member,
    ("budgets", "update"): _check_active_member,
    ("budgets", "delete"): _check_active_member,
    ("settlements", "insert"): _check_active_member,
    ("share_requests", "insert"): _check_active_member,
    ("share_requests", "delete"): _check_active_member,
    ("reconciliations", "insert"): _check_active_member,
    ("reconciliations", "update"): _check_active_member,
    ("reconciliations", "delete"): _check_active_member,
}


_UNKNOWN_TABLE: WriteErrorCode = "unknown_table"  # vocabulaire fermé ADR 0014 (D6)
_AUTH_DENIED: WriteErrorCode = "auth_denied"  # vocabulaire fermé ADR 0014 (D6)


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
    puis, pour une mutation neuve, frontière transactionnelle PAR MUTATION
    (S13.6) : handler (étapes 3-7) → append `sync_request_log` (étape 9) →
    `commit()` (étape 8) → ack (étape 10). Un échec rollback la mutation N SEULE ;
    1..N-1 restent committées et la boucle poursuit N+1 (ADR 0014).

    La session (UoW de l'appelant, ADR 0015) est threadée aux checks, au handler,
    à l'append et au `commit()` par mutation. `handlers` / `permission_checks` /
    `is_processed` injectables = couture de test + point d'enregistrement S13.4
    (défaut = registres / lookup module).
    """
    # `user` est DÉTACHÉ de la session avant la boucle : un `session.rollback()`
    # par-mutation (échec de N) EXPIRE sinon tous les objets persistants, et l'accès
    # SYNCHRONE à `user.id` au tour N+1 (étape 1) déclencherait un lazy-load →
    # `MissingGreenlet`. `get_current_user` charge la ligne complète (`session.get`,
    # `expire_on_commit=False`), donc l'objet détaché garde tous ses attributs en
    # mémoire (lecture sans IO) — seul `user.id` (UUID) est consommé en aval.
    if user in session:
        session.expunge(user)
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
            # Replay d'une mutation déjà commitée (étape 9) : ack SANS ré-écrire
            # (handler NON appelé) — idempotence stricte, scopée user.
            results.append(WriteResult(client_request_id=mutation.client_request_id, success=True))
            continue
        # Frontière transactionnelle PAR MUTATION (étape 8, ADR 0014 / D-A) : le write
        # (handler flush-only, étapes 3-7) + l'append du journal (étape 9, DANS la même
        # transaction, D-B) sont committés ENSEMBLE. Un échec rollback la mutation N
        # SEULE (1..N-1 restent committées) et la boucle poursuit N+1.
        # Hook delivery post-commit (email/push) = no-op tant que `notifications` est un
        # stub (aucun subscriber) : pas de `BackgroundTasks` ici (l'endpoint est S13.8, D-J).
        try:
            result = await handler(session, user, mutation)  # étapes 3-7 (flush-only)
            if result.success:
                await record_processed(  # étape 9 (in-tx, avant commit)
                    session,
                    user_id=user.id,
                    client_request_id=mutation.client_request_id,
                    table_name=mutation.table,
                )
                await session.commit()  # étape 8 (commit par mutation)
            # else : refus du handler SANS exception (ex. `reconciliations` →
            # `not_implemented_yet`). Contrat : un tel refus n'écrit RIEN. On NE
            # journalise pas et on NE committe pas (sinon un replay l'ack-erait à tort
            # `success=True`). Pas de `rollback()` non plus : il n'y a aucun write à
            # défaire, et un `commit` ultérieur du batch (ou de `get_db`) absorbera les
            # lectures read-only. Le résultat de refus est appendu tel quel.
        except Exception as exc:
            await session.rollback()  # rollback de N SEUL (1..N-1 committées)
            error = to_write_error(exc)  # exception domaine CONNUE → code typé (P13.6.3)
            if error is None:
                # Inconnue (erreur serveur, OU `ValidationError` de payload étape 3) :
                # PAS un faux `success` — on PROPAGE → 500 (retry PowerSync, D-H/D-I).
                # Les mutations 1..N-1 sont déjà committées (skip au retry, idempotence).
                raise
            results.append(
                WriteResult(
                    client_request_id=mutation.client_request_id, success=False, error=error
                )
            )
            continue  # erreur récupérable : le client purge la mutation, on poursuit N+1
        results.append(result)
    return results
