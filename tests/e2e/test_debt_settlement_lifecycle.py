"""E2E Parcours 5 — Debt → settlement lifecycle, covers E09 (debts) + E10 (settlements).

One black-box HTTP chain over the END-TO-END debt value, absent until now (neither
E09 nor E10 had an E2E API parcours): two members each enter a confirmed form-B
expense on their own personal account → each fires the real `share_request` flow
on the OTHER member → two `Debt`s are materialised in CROSSED directions
(`Bob→Alice` and `Alice→Bob`) → the oriented dashboard reads see both with full
`remaining_cents` and the correct signed net → an over-settlement is refused
end-to-end (422, debts UNCHANGED, verified by GET not just the status code) → a
legitimate `virtual` cross-netting settlement (positive line amounts, direction
borne by the debts' orientation — ADR 0011) fully nets one debt and partially the
other → conservation is observed (`remaining_cents == 0`) over HTTP AND persisted
(side-channel `compute_remaining`) → the settlement detail stays MASKED to the
debtor (`source_transaction_id`/`account_id` absent, `materialization_trace`
never exposed).

Per §6.3 this is the API anticipation of the `share_request` half of the
Playwright Parcours #4 (the F10 overflow half — `debt_generation_override`, E11 —
is out of scope, E11 not started). Per the anti-duplication guard (§12) it asserts
the CHAIN and the inter-module PROPAGATION (`share_request` → `Debt`
materialisation → `settlement` → remaining balance), NEVER the per-endpoint
contracts already covered by the S09.3 (#144) and S10.4 (#155) integration tiers:
the RBAC 404s, each `SettlementValidator` invariant in isolation, the schema
boundaries and the 401-anonymous guard stay delegated to integration.

The conservation invariant is read by a side-channel (D3): no HTTP endpoint
exposes the raw remaining balance independently of the S09.4 debtor masking, so
`fetch_debt_remaining` reads `compute_remaining` against the durable state. To be
replaced by an HTTP call once such an endpoint exists.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e._helpers import (
    auth_headers,
    bootstrap_admin,
    confirm_transaction,
    create_category,
    create_personal_account,
    create_settlement,
    create_share_request,
    create_transaction,
    fetch_debt_remaining,
    onboard_member,
    settlement_body,
    user_id_by_email,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

# Alice is the bootstrap admin, Bob an onboarded member (issue S10.6 §P10.6.1).
BOB_EMAIL = "debt-bob@example.com"
BOB_PASSWORD = "bob-password-123"

# Debt1 (Bob→Alice) is smaller than Debt2 (Alice→Bob): the cross-netting fully
# clears Debt1 and leaves a residue on Debt2, so conservation can be asserted on
# BOTH a zeroed and a partially-settled debt. With ratio 1.0 the debt equals the
# expense_total (Σ classification legs).
DEBT1_CENTS = 4000  # Bob owes Alice
DEBT2_CENTS = 6000  # Alice owes Bob


def _find_debt(items: list[dict[str, Any]], *, from_id: str, to_id: str) -> dict[str, Any]:
    """The unique debt in `items` oriented `from_id → to_id` (debtor → creditor)."""
    [debt] = [d for d in items if d["from_user_id"] == from_id and d["to_user_id"] == to_id]
    return debt


async def _confirmed_expense(
    client: Any, access: str, account_id: str, *, category_id: str, amount_cents: int
) -> str:
    """A confirmed form-B expense on `account_id` (funding leg + classification leg).

    Both legs on the SAME account → not a transfer → the classification leg must be
    categorised (E07/ADR 0017). `expense_total` = Σ classification legs = `amount_cents`,
    so a ratio-1.0 share_request materialises a debt of exactly `amount_cents`.
    Returns the confirmed transaction id (a valid `share_request` source).
    """
    tx = await create_transaction(
        client,
        access,
        account_id,
        splits=[
            {"account_id": account_id, "amount_cents": -amount_cents, "currency": "EUR"},
            {
                "account_id": account_id,
                "amount_cents": amount_cents,
                "currency": "EUR",
                "category_id": category_id,
            },
        ],
    )
    confirmed = await confirm_transaction(client, access, tx["id"])
    assert confirmed["state"] == "confirmed"
    return tx["id"]


async def test_debt_settlement_lifecycle(  # noqa: PLR0915 — E2E journey is deliberately long
    committed_client, committed_sessionmaker
) -> None:
    client = committed_client

    # 1. Foyer: Alice (admin) + Bob (member). Ids resolved side-channel (D3) — the
    #    share_request body carries the debtor id, the oriented reads assert
    #    orientation against both.
    alice_access, _refresh, alice_email = await bootstrap_admin(client)
    bob_access = await onboard_member(client, alice_access, BOB_EMAIL, BOB_PASSWORD)
    alice_id = str(await user_id_by_email(committed_sessionmaker, alice_email))
    bob_id = str(await user_id_by_email(committed_sessionmaker, BOB_EMAIL))

    # Household-scoped category for the form-B classification legs (both expenses).
    category = await create_category(client, alice_access, name="Courses")

    # 2. Debt1 (Bob→Alice): Alice (creditor) owns the source account + confirmed
    #    expense, then share_requests FROM Bob → materialises `from=Bob → to=Alice`.
    alice_account = await create_personal_account(client, alice_access, name="Alice perso")
    alice_tx = await _confirmed_expense(
        client,
        alice_access,
        alice_account["id"],
        category_id=category["id"],
        amount_cents=DEBT1_CENTS,
    )
    await create_share_request(
        client, alice_access, alice_tx, requested_from=bob_id, short_label="Courses Bob"
    )

    # 3. Debt2 (Alice→Bob), OPPOSITE direction: Bob (creditor) does the same FROM
    #    Alice → materialises `from=Alice → to=Bob`. The crossed sense requires each
    #    user to share from the other (issue §Notes).
    bob_account = await create_personal_account(client, bob_access, name="Bob perso")
    bob_tx = await _confirmed_expense(
        client, bob_access, bob_account["id"], category_id=category["id"], amount_cents=DEBT2_CENTS
    )
    await create_share_request(
        client, bob_access, bob_tx, requested_from=alice_id, short_label="Resto Alice"
    )

    # 4. Oriented reads (as Alice): both crossed debts are visible filtered on Bob,
    #    each at full `remaining_cents` (no settlement yet); the by-counterparty net
    #    is signed by orientation (Bob owes 4000, Alice owes 6000 → −2000 net).
    listed = (
        await client.get("/debts", params={"with": bob_id}, headers=auth_headers(alice_access))
    ).json()["items"]
    debt1 = _find_debt(listed, from_id=bob_id, to_id=alice_id)
    debt2 = _find_debt(listed, from_id=alice_id, to_id=bob_id)
    assert debt1["remaining_cents"] == DEBT1_CENTS
    assert debt2["remaining_cents"] == DEBT2_CENTS
    debt1_id, debt2_id = debt1["debt_id"], debt2["debt_id"]

    by_cp = (await client.get("/debts/by-counterparty", headers=auth_headers(alice_access))).json()[
        "items"
    ]
    [net_bob] = [n for n in by_cp if n["user_id"] == bob_id]
    assert net_bob["net_amount"] == DEBT1_CENTS - DEBT2_CENTS  # −2000: Alice owes Bob net
    assert net_bob["debts_count"] == 2

    # 5. Over-settlement REFUSED end-to-end: a single line apuring more than Debt1's
    #    remaining → 422 (SettlementValidator). Inline (not via the 201-asserting
    #    helper) since the negative case must assert the status itself.
    over = await client.post(
        "/settlements",
        json=settlement_body(type_="virtual", lines=[(debt1_id, DEBT1_CENTS + 1)]),
        headers=auth_headers(alice_access),
    )
    assert over.status_code == 422, over.text
    # …and the debts are UNCHANGED (verified by GET, not just the status code).
    after_refusal = (
        await client.get("/debts", params={"with": bob_id}, headers=auth_headers(alice_access))
    ).json()["items"]
    assert (
        _find_debt(after_refusal, from_id=bob_id, to_id=alice_id)["remaining_cents"] == DEBT1_CENTS
    )
    assert (
        _find_debt(after_refusal, from_id=alice_id, to_id=bob_id)["remaining_cents"] == DEBT2_CENTS
    )

    # 6. Legitimate virtual cross-netting: `type=virtual`, `linked_transaction_id=null`,
    #    lines on BOTH debts with POSITIVE amounts. Equal amounts in opposite
    #    orientations net to zero (ADR 0011): Debt1 fully cleared, Debt2 settled by
    #    4000 (residue 2000). The direction is borne by the debts, never a line sign.
    settlement = await create_settlement(
        client,
        alice_access,
        type_="virtual",
        lines=[(debt1_id, DEBT1_CENTS), (debt2_id, DEBT1_CENTS)],
    )
    assert settlement["linked_transaction_id"] is None
    assert settlement["created_by"] == alice_id

    # 7. Conservation observed over HTTP: Debt1 fully netted (remaining 0), Debt2
    #    partially (residue DEBT2 − DEBT1).
    final = (
        await client.get("/debts", params={"with": bob_id}, headers=auth_headers(alice_access))
    ).json()["items"]
    assert _find_debt(final, from_id=bob_id, to_id=alice_id)["remaining_cents"] == 0
    assert (
        _find_debt(final, from_id=alice_id, to_id=bob_id)["remaining_cents"]
        == DEBT2_CENTS - DEBT1_CENTS
    )

    # Detail MASKED to the debtor (S09.4/S10.4 propagated): Bob is the debtor of
    # Debt1 → its source fields are hidden; he is the creditor of Debt2 → those are
    # visible (positive control). `materialization_trace` is never exposed either way.
    detail = (
        await client.get(f"/settlements/{settlement['id']}", headers=auth_headers(bob_access))
    ).json()
    detail_debts = {d["debt_id"]: d for d in detail["debts"]}
    masked = detail_debts[debt1_id]
    assert masked["source_transaction_id"] is None
    assert masked["account_id"] is None
    assert "materialization_trace" not in masked
    visible = detail_debts[debt2_id]
    assert visible["source_transaction_id"] == bob_tx
    assert visible["account_id"] == bob_account["id"]
    assert "materialization_trace" not in visible

    # The settlement is listed between the two parties (as Alice, filtered on Bob).
    settlements = (
        await client.get(
            "/settlements", params={"with": bob_id}, headers=auth_headers(alice_access)
        )
    ).json()["items"]
    assert settlement["id"] in {s["id"] for s in settlements}

    # 8. Conservation PERSISTED (D3): `compute_remaining` against the durable state,
    #    independent of the masking-aware HTTP projection.
    assert await fetch_debt_remaining(committed_sessionmaker, debt_id=debt1_id) == 0
    assert (
        await fetch_debt_remaining(committed_sessionmaker, debt_id=debt2_id)
        == DEBT2_CENTS - DEBT1_CENTS
    )
