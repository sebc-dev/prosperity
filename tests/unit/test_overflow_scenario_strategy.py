"""Propriétés pures sur les strategies de scénario overflow S11.5 (P11.5.1.a).

Verrouille la COMPOSITION propre à S11.5 (forçage override, bornes tx/dates,
payer-membre, forme 2-membres pour la conservation D7) — périmètre `Stratégie de
tests §4.2` (Hypothesis sur le pur, sans DB).

⚠️ On NE re-teste PAS ici les invariants de la strategy réutilisée
`account_with_members_strategy` (Σ ratio == 1, ratios > 0, owner_id None,
acceptation par `AccountValidator`) : ils sont DÉJÀ verrouillés par
`test_accounts_strategies.py` (S05.5). Les re-prouver serait un doublon (review
m3) — S11.5 réutilise la strategy telle quelle (D6).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import hypothesis.strategies as st
from hypothesis import event, given
from hypothesis import target as hyp_target

from tests.strategies import OverflowScenario, overflow_scenario_strategy

# Bornes ancrées EN DUR (oracle indépendant) — ne pas importer les constantes
# privées de `strategies.py` qu'on vérifie justement (et évite `reportPrivateUsage`).
_PERIOD_START = date(2026, 6, 1)
_PERIOD_END = date(2026, 6, 30)
_AMOUNT_BOUND = 10**7
_MIN_MEMBERS = 2
_MAX_MEMBERS = 5


@given(sc=overflow_scenario_strategy())
def test_property_payer_is_member(sc: OverflowScenario) -> None:
    # Contrat porteur de la conservation D7 : le payeur EST un membre, sa quote-part
    # est connue (== celle du membre 0). Roster borné 2..5 (D11, max_members explicite).
    member_ids = {m.user_id for m in sc.account.members}
    assert sc.payer_user_id in member_ids
    assert sc.payer_user_id == sc.account.members[0].user_id  # identité exacte (créancier)
    assert sc.payer_ratio == sc.account.members[0].ratio
    assert _MIN_MEMBERS <= len(sc.account.members) <= _MAX_MEMBERS


@given(sc=overflow_scenario_strategy())
def test_property_tx_bounded(sc: OverflowScenario) -> None:
    # Terminaison + tx TOUJOURS dans la fenêtre mensuelle du budget (D11).
    # `event`/`target` PROUVENT l'atteignabilité des bornes (sinon l'assertion
    # resterait vraie même si la strategy se bloquait p. ex. à amount=1 — review T2,
    # gabarit test_budget_strategies).
    assert sc.txs  # min_size=1 garanti
    max_amount = 0
    for tx in sc.txs:
        assert 1 <= tx.amount_cents <= _AMOUNT_BOUND
        assert _PERIOD_START <= tx.on <= _PERIOD_END
        max_amount = max(max_amount, tx.amount_cents)
    hyp_target(float(max_amount), label="montant tx max observé")
    event(f"≥ moitié de la borne haute ({max_amount >= _AMOUNT_BOUND // 2})")
    event(f"borne basse (amount=1) atteinte ({any(tx.amount_cents == 1 for tx in sc.txs)})")
    event(f"début de fenêtre atteint ({any(tx.on == _PERIOD_START for tx in sc.txs)})")
    event(f"fin de fenêtre atteinte ({any(tx.on == _PERIOD_END for tx in sc.txs)})")


@given(data=st.data())
def test_property_override_forced_when_pinned(data: st.DataObject) -> None:
    # `override=ov` ⇒ TOUTES les tx portent `ov`, pour les TROIS valeurs du Literal
    # (les properties persistées `force_no_debt`/`force_full_debt` dépendent de ce
    # forçage ; `default` ferme la 3ᵉ branche — review T3). `st.data()` permet de
    # tirer le scénario avec l'override courant de la boucle.
    for ov in ("default", "force_no_debt", "force_full_debt"):
        sc = data.draw(overflow_scenario_strategy(override=ov))
        assert all(tx.override == ov for tx in sc.txs)


@given(sc=overflow_scenario_strategy())
def test_property_override_drawn_per_tx_when_unpinned(sc: OverflowScenario) -> None:
    # `override=None` (défaut) ⇒ chaque tx tire SON override parmi les 3 valeurs
    # licites — c'est le mode des properties persistées `default`/idempotence (review
    # T3). `event` prouve l'atteignabilité des 3 valeurs ET des scénarios mixtes
    # (overrides distincts dans un même scénario ⇒ tirage réellement PAR tx).
    valid = {"default", "force_full_debt", "force_no_debt"}
    assert all(tx.override in valid for tx in sc.txs)
    for v in sorted(valid):
        event(f"override {v} généré ({any(tx.override == v for tx in sc.txs)})")
    event(f"overrides mixtes intra-scénario ({len({tx.override for tx in sc.txs}) > 1})")


@given(sc=overflow_scenario_strategy(n_members=2, with_budget=True))
def test_property_two_member_form(sc: OverflowScenario) -> None:
    # Forme close D7 : exactement 2 membres (payer + autre), Σ ratio == 1 ⇒
    # `payer_ratio + s_o == 1` ; budget présent quand `with_budget=True`.
    assert len(sc.account.members) == 2  # noqa: PLR2004 — exactement payer + 1 débiteur
    assert sc.payer_ratio + sc.account.members[1].ratio == Decimal(1)
    assert sc.budget is not None


@given(data=st.data())
def test_property_budget_presence_and_roster_forced(data: st.DataObject) -> None:
    # `with_budget` pilote la présence du budget DANS LES DEUX SENS : le cas
    # « sans budget » (base = M côté prod, D9) n'avait aucune assertion (review Majeur).
    # `n_members` intermédiaire (4) est bien propagé au compte via le composite.
    sc_with = data.draw(overflow_scenario_strategy(with_budget=True, n_members=4))
    assert sc_with.budget is not None
    assert sc_with.budget.amount_cents >= 1
    assert len(sc_with.account.members) == 4  # noqa: PLR2004 — cardinalité intermédiaire

    sc_without = data.draw(overflow_scenario_strategy(with_budget=False))
    assert sc_without.budget is None
