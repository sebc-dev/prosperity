"""Intégration end-to-end — endpoint `POST /sync/upload` (S13.8, ADR 0014).

Pilote la route HTTP via `httpx` (`async_client` + `auth_schema` partagent une
connexion/transaction ; le rollback par-test révèle tout). La route est un boundary
PUR : elle authentifie (`get_current_user`), désérialise `BatchUpload`, délègue à
`process_batch` et renvoie `list[WriteResult]`. Les barrières (auth fail-closed
par-mutation, idempotence scopée user, erreurs typées) vivent dans le dispatcher
(S13.3→S13.6) — ici on prouve l'ASSEMBLAGE de bout en bout.

⚠️ Niveau (anti-duplication, M1 review du plan) : `async_client` tourne en
`join_transaction_mode="create_savepoint"`, donc le `commit()` PAR MUTATION du
dispatcher devient un *release* de SAVEPOINT. Ce tier prouve la SÉQUENCE, les ACKS
TYPÉS et les lectures intra-transaction ; il ne RE-PROUVE PAS la durabilité
post-commit « 1..N-1 persistent » — déjà verrouillée en S13.6 (tier `committed_engine`,
`test_sync_dispatcher_transaction.py`). On vérifie ici que la route DÉCLENCHE le même
chemin `process_batch`.

Les ids des `insert` sont GÉNÉRÉS SERVEUR (payloads `extra="forbid"` sans `id`) et
reportés dans `server_values["id"]` : une chaîne dépendante (create tx → add split →
confirm) se joue donc en POSTs SÉQUENTIELS threadant cet id (mime le client
PowerSync), pas en un seul batch (D1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.main import app
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.debts.models import Debt
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.schemas import MAX_MUTATIONS
from backend.modules.transactions.models import Split, Transaction

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]
Json = dict[str, Any]


# ── helpers ───────────────────────────────────────────────────────────────────
def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _seed_initialized_household(session: AsyncSession, *, base_currency: str = "EUR") -> None:
    """Seed an *initialised* singleton (`create_personal`/`create_category` read it)."""
    session.add(
        Household(
            name="Test Household",
            base_currency=base_currency,
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await session.flush()


def _mut(table: str, op: str, payload: Json, *, crid: str | None = None) -> Json:
    """One wire mutation (fresh `client_request_id` unless pinned, e.g. idempotence)."""
    return {
        "client_request_id": crid or str(uuid4()),
        "table": table,
        "op": op,
        "payload": payload,
    }


def _batch(*muts: Json) -> Json:
    return {"mutations": list(muts)}


async def _post(client: AsyncClient, headers: dict[str, str], *muts: Json) -> list[Json]:
    """POST a batch, assert 200, return the `WriteResult` list."""
    resp = await client.post("/sync/upload", json=_batch(*muts), headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _post_one(
    client: AsyncClient, headers: dict[str, str], table: str, op: str, payload: Json
) -> Json:
    """POST a single-mutation batch, assert success, return the lone `WriteResult`."""
    [res] = await _post(client, headers, _mut(table, op, payload))
    assert res["success"] is True, res
    return res


async def _count(session: AsyncSession, model: type, *whereclause: Any) -> int:
    stmt = select(func.count()).select_from(model).where(*whereclause)
    return int((await session.execute(stmt.execution_options(populate_existing=True))).scalar_one())


# ── 3.3.1 — chaîne dépendante réelle (server_values threadés) ───────────────────
async def test_upload_dependent_chain_threads_server_ids(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """AC « create account → create tx → add split → confirm → share_request ».

    Chaîne en POSTs séquentiels : chaque réponse fournit au suivant l'id serveur du
    parent (D1). Les deux jambes (funding `-N` sans catégorie + classification `+N`
    catégorisée, Σ == 0, ADR 0017) sont requises avant le confirm (`assert_zero_sum`).
    """
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-chain@ex.com")
    bob = await bound_user_factory(email="bob-chain@ex.com")  # débiteur, membre actif
    h = _bearer(alice.id)

    account_id = (
        await _post_one(
            async_client,
            h,
            "accounts",
            "insert",
            {"name": "Courant", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]
    category_id = (await _post_one(async_client, h, "categories", "insert", {"name": "Courses"}))[
        "server_values"
    ]["id"]
    tx_id = (
        await _post_one(async_client, h, "transactions", "insert", {"account_id": account_id})
    )["server_values"]["id"]

    # POST #4+#5 — les deux jambes équilibrées, un seul batch (ids connus).
    funding, classification = await _post(
        async_client,
        h,
        _mut(
            "splits",
            "insert",
            {
                "transaction_id": tx_id,
                "account_id": account_id,
                "amount_cents": -1500,
                "currency": "EUR",
            },
        ),
        _mut(
            "splits",
            "insert",
            {
                "transaction_id": tx_id,
                "account_id": account_id,
                "amount_cents": 1500,
                "currency": "EUR",
                "category_id": category_id,
            },
        ),
    )
    assert funding["success"] is True, funding
    assert classification["success"] is True, classification

    # POST #6 — confirm via le chemin légal draft → planned → confirmed
    # (STATE_TRANSITIONS : pas de saut direct draft → confirmed). Σ == 0,
    # classification catégorisée → les deux transitions passent.
    await _post_one(async_client, h, "transactions", "update", {"id": tx_id, "state": "planned"})
    await _post_one(async_client, h, "transactions", "update", {"id": tx_id, "state": "confirmed"})

    # POST #7 — share_request vers Bob (matérialise un Debt, ADR 0002).
    [sr] = await _post(
        async_client,
        h,
        _mut(
            "share_requests",
            "insert",
            {
                "transaction_id": tx_id,
                "requested_from": str(bob.id),
                "ratio": "0.5",
                "short_label": "diner",
            },
        ),
    )
    assert sr["success"] is True, sr

    # Oracle MINIMAL (n1) : le Debt du share_request existe (présence, pas montant —
    # l'antisymétrie/montant sont couverts S11/S13.5, anti-duplication).
    assert await _count(auth_schema, Debt, Debt.source_transaction_id == UUID(tx_id)) >= 1


# ── 3.3.2 — batch ordonné unique + idempotence au re-POST ───────────────────────
async def test_upload_single_ordered_batch_is_idempotent_on_repost(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """Un batch ordonné (les jambes AVANT le confirm) sur une tx draft pré-seedée +
    un `accounts/insert` indépendant. Re-POST du MÊME batch (mêmes `client_request_id`)
    ⇒ idempotent : acks `success`, 0 nouvelle écriture (replay strict, étape 2)."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-batch@ex.com")
    h = _bearer(alice.id)

    account_id = (
        await _post_one(
            async_client,
            h,
            "accounts",
            "insert",
            {"name": "Cpt", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]
    category_id = (await _post_one(async_client, h, "categories", "insert", {"name": "Cat"}))[
        "server_values"
    ]["id"]
    tx_id = (
        await _post_one(async_client, h, "transactions", "insert", {"account_id": account_id})
    )["server_values"]["id"]

    muts = [
        _mut(
            "splits",
            "insert",
            {
                "transaction_id": tx_id,
                "account_id": account_id,
                "amount_cents": -2000,
                "currency": "EUR",
            },
        ),
        _mut(
            "splits",
            "insert",
            {
                "transaction_id": tx_id,
                "account_id": account_id,
                "amount_cents": 2000,
                "currency": "EUR",
                "category_id": category_id,
            },
        ),
        # confirm via le chemin légal draft → planned → confirmed (pas de saut direct).
        _mut("transactions", "update", {"id": tx_id, "state": "planned"}),
        _mut("transactions", "update", {"id": tx_id, "state": "confirmed"}),
        _mut("accounts", "insert", {"name": "Autre", "type": "courant", "currency": "EUR"}),
    ]

    resp1 = await async_client.post("/sync/upload", json={"mutations": muts}, headers=h)
    assert resp1.status_code == 200, resp1.text
    results1 = resp1.json()
    assert len(results1) == 5
    # ordering préservé : les acks s'alignent sur l'ordre des `client_request_id` envoyés.
    assert [r["client_request_id"] for r in results1] == [m["client_request_id"] for m in muts]
    assert all(r["success"] for r in results1), results1

    splits_after = await _count(auth_schema, Split, Split.transaction_id == UUID(tx_id))
    accounts_after = await _count(auth_schema, Account, Account.owner_id == alice.id)
    log_after = await _count(auth_schema, SyncRequestLog, SyncRequestLog.user_id == alice.id)
    assert splits_after == 2
    assert accounts_after == 2  # le compte de setup + l'`accounts/insert` du batch

    # Re-POST identique → idempotent, 0 nouvelle écriture.
    resp2 = await async_client.post("/sync/upload", json={"mutations": muts}, headers=h)
    assert resp2.status_code == 200, resp2.text
    assert all(r["success"] for r in resp2.json()), resp2.text

    assert await _count(auth_schema, Split, Split.transaction_id == UUID(tx_id)) == splits_after
    assert await _count(auth_schema, Account, Account.owner_id == alice.id) == accounts_after
    assert (
        await _count(auth_schema, SyncRequestLog, SyncRequestLog.user_id == alice.id) == log_after
    )


# ── 3.3.3 — mutation invalide → erreur typée, les autres committées, pas de 500 ──
async def test_upload_mixed_valid_invalid_returns_typed_errors_no_500(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """Erreurs STRUCTURELLES (`unknown_table`, `auth_denied`) ET DOMAINE
    (`unbalanced_transaction`) curées en `WriteResult.error` typé dans le 200 — jamais
    un 500 global ; la suite du batch poursuit (ADR 0014)."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-mix@ex.com")
    bob = await bound_user_factory(email="bob-mix@ex.com")
    ha = _bearer(alice.id)
    bob_acc = (
        await _post_one(
            async_client,
            _bearer(bob.id),
            "accounts",
            "insert",
            {"name": "Bob", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]

    res = await _post(
        async_client,
        ha,
        _mut("accounts", "insert", {"name": "A1", "type": "courant", "currency": "EUR"}),
        _mut("not_a_table", "insert", {}),
        _mut("transactions", "insert", {"account_id": bob_acc}),  # Alice sur le compte de Bob
        _mut("accounts", "insert", {"name": "A2", "type": "courant", "currency": "EUR"}),
    )
    assert res[0]["success"] is True
    assert res[1]["success"] is False and res[1]["error"]["code"] == "unknown_table"
    assert res[2]["success"] is False and res[2]["error"]["code"] == "auth_denied"
    assert res[3]["success"] is True
    # les deux comptes valides existent ; rien sur le compte de Bob.
    assert await _count(auth_schema, Account, Account.owner_id == alice.id) == 2
    assert await _count(auth_schema, Transaction, Transaction.account_id == UUID(bob_acc)) == 0

    # Variante DOMAINE : une tx à une seule jambe (déséquilibrée) dont on demande la
    # transition draft → planned → `unbalanced_transaction` typé (le contrôle Σ == 0
    # se joue à la transition, cf. handler S13.4).
    acc = (
        await _post_one(
            async_client,
            ha,
            "accounts",
            "insert",
            {"name": "D", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]
    tx = (await _post_one(async_client, ha, "transactions", "insert", {"account_id": acc}))[
        "server_values"
    ]["id"]
    await _post_one(
        async_client,
        ha,
        "splits",
        "insert",
        {"transaction_id": tx, "account_id": acc, "amount_cents": -500, "currency": "EUR"},
    )
    [planned] = await _post(
        async_client, ha, _mut("transactions", "update", {"id": tx, "state": "planned"})
    )
    assert planned["success"] is False
    assert planned["error"]["code"] == "unbalanced_transaction"


# ── 3.3.4 — authentification requise ────────────────────────────────────────────
async def test_upload_requires_authentication(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """401 (uniforme, `WWW-Authenticate: Bearer`) sans token / token malformé / token
    signé pour un user inexistant. Aucune écriture dans les trois cas."""
    await _seed_initialized_household(auth_schema)
    batch = _batch(_mut("accounts", "insert", {"name": "X", "type": "courant", "currency": "EUR"}))

    no_header = await async_client.post("/sync/upload", json=batch)
    assert no_header.status_code == 401
    assert no_header.headers.get("www-authenticate") == "Bearer"

    bad_token = await async_client.post(
        "/sync/upload", json=batch, headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert bad_token.status_code == 401

    ghost = await async_client.post("/sync/upload", json=batch, headers=_bearer(uuid4()))
    assert ghost.status_code == 401

    assert await _count(auth_schema, SyncRequestLog) == 0


# ── 3.3.5 — auth_denied par mutation, sans fuite ────────────────────────────────
async def test_upload_per_mutation_auth_denied_does_not_leak(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """Alice mute le compte de Bob → `auth_denied`, 200, message STATIQUE (aucun
    `str(exc)`/id de Bob), aucune row écrite (fail-closed)."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-deny@ex.com")
    bob = await bound_user_factory(email="bob-deny@ex.com")
    bob_acc = (
        await _post_one(
            async_client,
            _bearer(bob.id),
            "accounts",
            "insert",
            {"name": "Bob", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]

    [res] = await _post(
        async_client, _bearer(alice.id), _mut("transactions", "insert", {"account_id": bob_acc})
    )
    assert res["success"] is False
    assert res["error"]["code"] == "auth_denied"
    assert res["error"]["message"] == "Not authorized."  # statique
    assert str(bob_acc) not in res["error"]["message"]
    assert await _count(auth_schema, Transaction, Transaction.account_id == UUID(bob_acc)) == 0


# ── 3.3.6 — enveloppe malformée → 422 (avant tout traitement) ───────────────────
async def test_upload_malformed_envelope_is_422(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """`op` hors enum / champ parasite (`extra="forbid"`) / `> MAX_MUTATIONS` → 422
    (Pydantic, AVANT le dispatcher). Aucune écriture."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-422@ex.com")
    h = _bearer(alice.id)

    bad_op = {
        "mutations": [
            {"client_request_id": str(uuid4()), "table": "accounts", "op": "upsert", "payload": {}}
        ]
    }
    assert (await async_client.post("/sync/upload", json=bad_op, headers=h)).status_code == 422

    extra = {"mutations": [], "foo": "bar"}
    assert (await async_client.post("/sync/upload", json=extra, headers=h)).status_code == 422

    too_many = {
        "mutations": [
            _mut("accounts", "insert", {"name": "x", "type": "courant", "currency": "EUR"})
            for _ in range(MAX_MUTATIONS + 1)
        ]
    }
    assert (await async_client.post("/sync/upload", json=too_many, headers=h)).status_code == 422

    assert await _count(auth_schema, SyncRequestLog) == 0


# ── 3.3.7 — batch vide → 200 [] ─────────────────────────────────────────────────
async def test_upload_empty_batch_is_noop_200(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-empty@ex.com")
    resp = await async_client.post(
        "/sync/upload", json={"mutations": []}, headers=_bearer(alice.id)
    )
    assert resp.status_code == 200
    assert resp.json() == []
    assert await _count(auth_schema, SyncRequestLog, SyncRequestLog.user_id == alice.id) == 0


# ── 3.3.8 — la route est enregistrée au composition root ────────────────────────
def test_sync_router_registered_at_composition_root() -> None:
    """Verrou que `include_router(sync_router)` n'a pas été oublié dans `main`."""
    route = next((r for r in app.router.routes if getattr(r, "path", None) == "/sync/upload"), None)
    assert route is not None, "POST /sync/upload absent de l'app"
    assert "POST" in route.methods  # type: ignore[attr-defined]


# ── 3.3.9 — idempotence scopée par user (ferme l'oracle cross-user) ─────────────
async def test_upload_idempotence_is_scoped_per_user(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """Un `client_request_id` commité par A ne valide PAS l'idempotence de B : B
    EXÉCUTE réellement sa mutation (pas un replay-ack). Le log est scopé `(user_id,
    client_request_id)` (models.py)."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-iso@ex.com")
    bob = await bound_user_factory(email="bob-iso@ex.com")
    ha, hb = _bearer(alice.id), _bearer(bob.id)
    acc_a = (
        await _post_one(
            async_client,
            ha,
            "accounts",
            "insert",
            {"name": "A", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]
    acc_b = (
        await _post_one(
            async_client,
            hb,
            "accounts",
            "insert",
            {"name": "B", "type": "courant", "currency": "EUR"},
        )
    )["server_values"]["id"]

    crid = str(uuid4())
    [res_a] = await _post(
        async_client, ha, _mut("transactions", "insert", {"account_id": acc_a}, crid=crid)
    )
    assert res_a["success"] is True

    # B poste le MÊME client_request_id sur SON compte → exécution réelle, pas replay.
    [res_b] = await _post(
        async_client, hb, _mut("transactions", "insert", {"account_id": acc_b}, crid=crid)
    )
    assert res_b["success"] is True
    assert res_b["server_values"]["id"] is not None  # un vrai draft créé pour B (≠ replay-ack)

    assert await _count(auth_schema, Transaction, Transaction.account_id == UUID(acc_b)) == 1
    assert (
        await _count(
            auth_schema,
            SyncRequestLog,
            SyncRequestLog.user_id == bob.id,
            SyncRequestLog.client_request_id == UUID(crid),
        )
        == 1
    )


# ── 3.3.10 — exception NON mappée → 500, la route mince ne l'avale pas (D2) ──────
async def test_upload_unmapped_exception_propagates_500(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
    monkeypatch: Any,
) -> None:
    """Verrou de D2 : une erreur serveur non mappée propage en 500 (retry PowerSync),
    JAMAIS un faux 200. Corps GÉNÉRIQUE (défaut Starlette non-debug : pas de
    stacktrace, pas du détail interne). `async_client` installe l'override `get_db` ;
    on observe le 500 via un transport `raise_app_exceptions=False`."""
    await _seed_initialized_household(auth_schema)
    alice = await bound_user_factory(email="alice-500@ex.com")

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom internal detail")

    monkeypatch.setattr("backend.modules.sync.transports.http.process_batch", _boom)
    batch = _batch(_mut("accounts", "insert", {"name": "X", "type": "courant", "currency": "EUR"}))

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sync/upload", json=batch, headers=_bearer(alice.id))

    assert resp.status_code == 500
    assert "boom internal detail" not in resp.text  # aucune fuite du détail interne
