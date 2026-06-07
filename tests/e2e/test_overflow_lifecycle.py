"""E2E Parcours 4 (moitié overflow F10) — debt_generation_override lifecycle, couvre E11.

The F10 overflow half of the Playwright Parcours #4 « Cycle de dette complet »
(§6.2), explicitly deferred by `test_debt_settlement_lifecycle.py` (« the F10
overflow half — `debt_generation_override`, E11 — is out of scope, E11 not
started »). E11 livré (S11.1→S11.5) ⇒ ce parcours le complète : une seule chaîne
HTTP boîte-noire sur la valeur de bout en bout, depuis le client public.

Le livrable agrégé du roadmap E11, joué par-dessus l'API réelle : Alice paie 100 €
Courses depuis le compte commun 50/50 alors que le budget Courses a 50 € → 50 €
d'excédent matérialise 25 € de dette Bob → Alice (`default`) ; Alice marque la tx
`force_full_debt` → 100 € entiers matérialisent 50 € ; un `void` supprime la dette
overflow.

Per §6.3 ce tier valide la **chaîne de valeur HTTP** : les schémas de requête
(`extra=forbid`), l'auth Bearer, les routes FastAPI, le `dispatch` synchrone du
materializer (ADR 0015) dans la transaction de la requête, ET la projection de
lecture `GET /debts` (orientation *débiteur → payeur*, `origin`, masquage S09.4).
Per l'anti-duplication (§12) il asserte la CHAÎNE et la propagation inter-modules
(`confirm`/`edit`/`void` → materializer → `Debt` overflow → lecture orientée),
JAMAIS ce qui est déjà couvert plus bas : le calcul `compute_for_overflow` (unit
`test_debts_overflow`), la fenêtre ordonnée / upsert-prune / idempotence
(intégration `test_overflow_materializer`), les invariants Hypothesis persistés
(S11.5 `test_overflow_invariants_property`), l'index partiel (tier migrations).

Câblage (gabarit `test_budget_lifecycle._wire_threshold_detector_e2e`) : le
`subscribe_async` du composition root vit dans le `lifespan` de `main.py`, qui ne
tourne PAS sous `ASGITransport` (`committed_client`) ; la fixture autouse
`_wire_overflow_e2e` `clear_subscribers()` puis re-souscrit les trois handlers
overflow, exactement comme l'intégration et l'E2E budget. `subscribe_async` est
idempotent.

Seeds en forme canonique B (ADR 0017) : funding leg (`category_id=NULL`, −M) +
classification leg (`category_id=Courses`, +M) sur le MÊME compte commun → pas un
transfert → la jambe classification est catégorisée et porte l'`expense_total`.
Le budget est `scope="shared"` avec Alice ET Bob contributeurs (sous-ensemble des
members du compte) — sinon `_eligible_account_ids` exclurait le compte commun et
l'overflow se résoudrait « sans budget » (base = M).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from backend.modules.debts.service.overflow_materializer import (
    materialize_overflow,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.shared.events import clear_subscribers, subscribe_async
from tests.e2e._helpers import (
    auth_headers,
    bootstrap_admin,
    confirm_transaction,
    create_budget,
    create_category,
    create_shared_account,
    create_transaction,
    onboard_member,
    patch_transaction,
    user_id_by_email,
    void_transaction,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

BOB_EMAIL = "overflow-bob@example.com"
BOB_PASSWORD = "bob-password-123"

_OVERFLOW = "shared_account_overflow"

# 100 € expense over a 50 € budget on a 50/50 shared account, Alice the payer.
EXPENSE_CENTS = 10000
BUDGET_CENTS = 5000
# `default` overflow: E = max(0, 100 − 50) = 50 € ; Bob's 0.5 share of E = 25 €
# (the payer Alice never owes herself — Σ debts == E × (1 − creator_share)).
DEFAULT_DEBT_CENTS = 2500
# `force_full_debt`: budget court-circuité, base = M ; Bob's 0.5 share of 100 € = 50 €.
FULL_DEBT_CENTS = 5000


@pytest.fixture(autouse=True)
def _wire_overflow_e2e() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-subscribe the three overflow handlers on the bus (the `lifespan`
    câblage does not run under `ASGITransport`). Cold bus before AND after
    (process-global state); `subscribe_async` is idempotent."""
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    subscribe_async(TransactionVoidedEvent, remove_overflow_on_void)
    subscribe_async(TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit)
    yield
    clear_subscribers()


def _today() -> date:
    # UTC anchor (gabarit `test_budget_lifecycle._today`): the tx date defaults to
    # `datetime.now(UTC).date()` and the overflow context resolves its window with
    # the same clock — pin both here so the expense can't straddle the UTC-midnight
    # boundary on a CI runner in a negative timezone (→ tx out of window → flake).
    return datetime.now(UTC).date()


async def _overflow_debts(
    client: AsyncClient, access: str, *, with_id: str
) -> list[dict[str, Any]]:
    """The `shared_account_overflow` debts visible to `access` filtered on `with_id`.

    Reads the real public projection (`GET /debts?with=…`), then filters the origin
    in the test (a co-present `personal_share_request` would ride the same list)."""
    resp = await client.get("/debts", params={"with": with_id}, headers=auth_headers(access))
    assert resp.status_code == 200, resp.text
    return [d for d in resp.json()["items"] if d["origin"] == _OVERFLOW]


async def test_overflow_lifecycle(committed_client, committed_sessionmaker) -> None:
    client = committed_client

    # 1. Foyer: Alice (admin, payer/creditor) + Bob (member, debtor). Ids resolved
    #    side-channel (D3) to assert the debt orientation against both.
    alice_access, _refresh, alice_email = await bootstrap_admin(client)
    await onboard_member(client, alice_access, BOB_EMAIL, BOB_PASSWORD)
    alice_id = str(await user_id_by_email(committed_sessionmaker, alice_email))
    bob_id = str(await user_id_by_email(committed_sessionmaker, BOB_EMAIL))

    # 2. Household category + 50/50 shared account (Alice creates it; both members).
    category = await create_category(client, alice_access, name="Courses")
    shared = await create_shared_account(
        client,
        alice_access,
        name="Compte commun",
        members=[
            {"user_id": alice_id, "default_share_ratio": "0.5"},
            {"user_id": bob_id, "default_share_ratio": "0.5"},
        ],
    )

    # 3. Budget Courses 50 €, scope shared, BOTH members contributors (else the
    #    shared account is not eligible and the overflow resolves « sans budget »).
    period_start = _today().replace(day=1).isoformat()
    as_of = _today().isoformat()
    await create_budget(
        client,
        alice_access,
        category_id=category["id"],
        period_start=period_start,
        amount_cents=BUDGET_CENTS,
        contributor_ids=[alice_id, bob_id],
        scope="shared",
    )

    # 4. Alice confirms a 100 € form-B expense on the shared account, classified to
    #    Courses. The date is pinned to `as_of` (UTC) so it lands inside the window.
    tx = await create_transaction(
        client,
        alice_access,
        shared["id"],
        date=as_of,
        splits=[
            {"account_id": shared["id"], "amount_cents": -EXPENSE_CENTS, "currency": "EUR"},
            {
                "account_id": shared["id"],
                "amount_cents": EXPENSE_CENTS,
                "currency": "EUR",
                "category_id": category["id"],
            },
        ],
    )
    confirmed = await confirm_transaction(client, alice_access, tx["id"])
    assert confirmed["state"] == "confirmed"

    # 5. `default` overflow materialised over HTTP: a single debt Bob → Alice of 25 €
    #    (E = 50 € × Bob's 0.5 share), readable via the public oriented projection.
    debts = await _overflow_debts(client, alice_access, with_id=bob_id)
    assert len(debts) == 1, debts
    [debt] = debts
    assert (debt["from_user_id"], debt["to_user_id"]) == (bob_id, alice_id)
    assert debt["amount_cents"] == DEFAULT_DEBT_CENTS
    assert debt["remaining_cents"] == DEFAULT_DEBT_CENTS  # no settlement yet
    # Overflow debts mask `source_transaction_id`/`account_id` for BOTH parties: the
    # E11 source-ownership rule is not wired yet, so `_reader_owns_source` fail-safes
    # to masked (`dashboard.py`). Pinned here at the public read projection.
    assert debt["source_transaction_id"] is None
    assert debt["account_id"] is None
    debt_id = debt["debt_id"]
    # Alice (the payer) never owes herself: filtered `owed_by_me`, she has no overflow
    # debt as debtor (Σ debts == E × (1 − creator_share); the payer is excluded).
    owed_by_alice = (
        await client.get(
            "/debts", params={"direction": "owed_by_me"}, headers=auth_headers(alice_access)
        )
    ).json()["items"]
    assert [d for d in owed_by_alice if d["origin"] == _OVERFLOW] == []

    # 6. `force_full_debt` over HTTP: PATCH the override → the materializer recomputes
    #    on the same row (`ON CONFLICT DO UPDATE`, idempotent) — budget court-circuité,
    #    base = 100 € ⇒ the debt grows to 50 €, SAME debt_id (no duplicate row).
    await patch_transaction(
        client, alice_access, tx["id"], debt_generation_override="force_full_debt"
    )
    debts = await _overflow_debts(client, alice_access, with_id=bob_id)
    assert len(debts) == 1, debts
    [full] = debts
    assert full["debt_id"] == debt_id
    assert full["amount_cents"] == FULL_DEBT_CENTS
    assert (full["from_user_id"], full["to_user_id"]) == (bob_id, alice_id)

    # 7. `void` over HTTP: the tx's overflow debt is removed end-to-end.
    voided = await void_transaction(client, alice_access, tx["id"])
    assert voided["state"] == "void"
    assert await _overflow_debts(client, alice_access, with_id=bob_id) == []
