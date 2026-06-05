"""Properties Hypothesis PUR-DOMAINE du `SettlementValidator` (S10.5).

Verrouille les invariants structurants du règlement sur le validateur **pur**
(S10.2) — JAMAIS au-dessus de `create_settlement` (effet de bord DB) : le
property-based sur effets de bord est flaky (`Stratégie de tests` §12) ⇒ les
invariants PERSISTÉS passent en example-based d'intégration
(`tests/integration/test_settlement_conservation.py`).

**Conservation du solde net** (P10.5.1) — pour tout scénario apuré exactement, le
validateur ACCEPTE et calcule le net orienté canonique conforme au type (`0` si
virtual équilibré, `== montant viré` sinon). C'est l'aboutissement de la property
zero-sum non-dégénérée DIFFÉRÉE par S09.5 (#146) : l'ensemble des dettes ciblées
n'est plus un singleton.

NE redéploie PAS S10.2 (qui teste le validateur PAR APPEL, un négatif par règle) :
ici on teste les PROPRIÉTÉS ÉMERGENTES sur l'espace généré (acceptation + net
conservé). `max_examples` n'est PAS fixé : hérité du profil chargé au boot par
`conftest.py` (`load_profile` → `settings.default`) ⇒ ci=50 / nightly=500 /
default=100. Un run vert sans `filter_too_much` EST la preuve que la strategy est
SANS rejet (§4.2 ; Stratégie §9.2/9.3).
"""

from __future__ import annotations

from uuid import UUID

from hypothesis import HealthCheck, example, given, settings

from backend.modules.debts.domain import (
    DebtContext,
    SettlementLineInput,
    SettlementValidator,
)
from tests.strategies import SettlementScenario, settlement_scenario_strategy

# Nettage croisé symétrique virtual A→B 50 / B→A 50 → net 0 (épingle la conservation).
_VIRT_SYM = SettlementScenario(
    "virtual",
    (
        DebtContext(
            debt_id=UUID(int=10),
            from_user_id=UUID(int=1),
            to_user_id=UUID(int=2),
            currency="EUR",
            remaining_cents=50,
        ),
        DebtContext(
            debt_id=UUID(int=11),
            from_user_id=UUID(int=2),
            to_user_id=UUID(int=1),
            currency="EUR",
            remaining_cents=50,
        ),
    ),
    (
        SettlementLineInput(debt_id=UUID(int=10), amount_cents=50),
        SettlementLineInput(debt_id=UUID(int=11), amount_cents=50),
    ),
    None,
    0,
)

# Non-virtuel cross-direction A→B 50 / B→A 20 → net orienté 30 ≠ 0 : donne du
# POUVOIR DISCRIMINANT à l'assertion de net (lo=UUID(int=1), hi=UUID(int=2) :
# A→B 50 [+50] + B→A 20 [-20] = +30 ; internal_transfer, linked == abs(net) == 30).
_INT_PARTIAL = SettlementScenario(
    "internal_transfer",
    (
        DebtContext(
            debt_id=UUID(int=20),
            from_user_id=UUID(int=1),
            to_user_id=UUID(int=2),
            currency="EUR",
            remaining_cents=50,
        ),
        DebtContext(
            debt_id=UUID(int=21),
            from_user_id=UUID(int=2),
            to_user_id=UUID(int=1),
            currency="EUR",
            remaining_cents=20,
        ),
    ),
    (
        SettlementLineInput(debt_id=UUID(int=20), amount_cents=50),
        SettlementLineInput(debt_id=UUID(int=21), amount_cents=20),
    ),
    30,
    30,
)


class TestConservationProperty:
    # `max_examples` n'est PAS fixé ici : hérité du profil chargé au boot par
    # `conftest.py` (`load_profile` → `settings.default`) ⇒ ci=50 / nightly=500 /
    # default=100 (D5 ; écart de convention volontaire, profils = source unique).
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(scenario=_VIRT_SYM)  # nettage croisé symétrique virtual (net 0)
    @example(scenario=_INT_PARTIAL)  # non-virtuel, net 30 ≠ 0 (discriminant)
    @given(scenario=settlement_scenario_strategy())
    def test_validator_accepts_balanced_scenario_with_conserved_net(
        self, scenario: SettlementScenario
    ) -> None:
        # Self-test de contrat de la strategy (AC « 2 contreparties » + devise
        # unique). NB : ce n'est PAS une couverture de l'invariant
        # `MultipleCounterpartiesError` (anti-tiers), qui reste couvert PAR APPEL
        # en S10.2 — la strategy ne génère QUE {lo, hi} (cf. plan §6).
        assert len(scenario.counterparties) == 2  # noqa: PLR2004 — exactement {A, B}
        assert {c.currency for c in scenario.debt_contexts} == {"EUR"}

        # CŒUR PROBANT : le validateur ACCEPTE (ne lève AUCUNE
        # SettlementValidationError) et calcule le NET ORIENTÉ CANONIQUE conforme
        # au type. C'est l'invariant « conservation du solde net » au sens du
        # validateur : un scénario apuré exactement nette à 0 (virtual) / au
        # montant viré (non-virtuel). On n'asserte PAS un `remaining_after`
        # recalculé en Python : l'apurement complet le rendrait 0 PAR CONSTRUCTION
        # de la strategy, sans rien prouver du validateur. La conservation
        # PERSISTÉE (round-trip DB) est verrouillée en intégration (§12).
        result = SettlementValidator.validate(
            settlement_type=scenario.settlement_type,
            lines=scenario.lines,
            debt_contexts=scenario.contexts_by_id,
            linked_transaction_amount_cents=scenario.linked_transaction_amount_cents,
        )
        assert result.net_transfer_cents == scenario.expected_net_transfer_cents
        assert result.counterparties == scenario.counterparties
        assert result.type == scenario.settlement_type
