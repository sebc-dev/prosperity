"""Contrat des stratégies `debts` (S09.5, P09.5.1) — Hypothesis PUR-DOMAINE.

NE redéploie PAS les invariants du `DebtCalculator` : ils sont CLOS par S09.2
(`test_debts_domain.py` : déterminisme, idempotence, antisymétrie-proxy,
bornes, no-self-debt, rejet ratio) — cf. review #146 (M1/M2). Rôle unique :
VALIDER le contrat des stratégies que E10 (properties zero-sum du Settlement)
consommera — qu'elles produisent, sur TOUT l'espace généré et SANS rejet, une
`Debt` valide. Un run `ci=50` / `nightly=500` vert sans `filter_too_much` EST
le test de la strategy (§4.2 ; Stratégie §9.2/9.3).
"""

from __future__ import annotations

from hypothesis import given

from backend.modules.debts.domain import Debt
from tests.strategies import debt_strategy


class TestDebtStrategyContract:
    @given(debt=debt_strategy())
    def test_strategy_yields_valid_oriented_debt(self, debt: Debt) -> None:
        # Contrat consommé par E10 : (a) la strategy ne lève JAMAIS pendant le
        # draw (borne basse ⇒ pas d'arrondi→0) — le simple fait que `@given`
        # produise un `debt` le prouve ; (b) paire distincte (distinct_uuid_pair)
        # ⇒ from != to ; (c) montant strictement positif. Garde structurelle,
        # PAS un invariant neuf du calculator (couvert S09.2).
        assert debt.from_user_id != debt.to_user_id
        assert debt.amount.amount_cents >= 1
