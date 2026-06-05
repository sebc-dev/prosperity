# E10 — Settlements (multi-line, 3 types)

> **Durée estimée** : 4-5 jours
> **Statut** : not started
> **Dépend de** : E09
> **Bloque** : E11 (overflow F10 utilise les mêmes calculs de solde restant)
> **ADRs activés** : 0011 (`Settlement` multi-line, pas d'état sur `Debt`)

---

## Objectif

Implémenter F09 partie 2 : `Settlement` + `SettlementLine` comme entités dédiées avec 3 `type` (`internal_transfer`, `external_transfer`, `virtual`) + nettage multi-debts bidirectionnel + invariants Hypothesis (conservation solde net).

Livrable agrégé : Bob crée un Settlement `virtual` qui apure 3 dettes en sens croisés avec Alice. Le solde restant de chaque dette se calcule par différence — pas d'état sur `Debt`.

---

## Stories

### S10.1 — Modèles `Settlement` + `SettlementLine`

| Phase | Description | Diff |
|---|---|---|
| **P10.1.1** | Modèle `Settlement` : `id`, `household_id`, `created_by`, `created_at`, `settled_at` date, `type` Literal, `linked_transaction_id` FK NULL, `note` text. Modèle `SettlementLine` : `id`, `settlement_id` FK CASCADE, `debt_id` FK, `amount_cents` bigint (signé). Index `(debt_id)` | ~120 |
| **P10.1.2** | Migration `0015_settlements.py` (`0012`/`0013`/`0014` pris : budget alerts, leg_role, debts). Test niveau 1 schema check | ~80 |

---

### S10.2 — Domain + service de validation

**Livrable observable** : `debts.public.create_settlement(...)` valide les invariants avant insert.

| Phase | Description | Diff |
|---|---|---|
| **P10.2.1** | `debts/domain.py` étend : `SettlementValidator` pur. Règles : (1) `sum(SettlementLine.amount_cents) == abs(linked_transaction.amount)` pour types non-virtuels, (2) tous les `debt_id` référencent des dettes entre les **deux mêmes** contreparties, (3) `linked_transaction_id IS NULL` pour `virtual`, NOT NULL pour les deux autres, (4) tous les `debt_id` doivent encore avoir un solde restant > 0. Tests example | ~200 |
| **P10.2.2** | Service `debts/service/settlement.py` : `create_settlement(type, linked_tx_id, lines, by_user, settled_at)` — valide, insert Settlement + N SettlementLine en transaction DB. Tests intégration | ~250 |

---

### S10.3 — Calcul du solde restant d'une `Debt`

**Livrable observable** : `debts.public.compute_remaining(debt_id) → int` retourne le restant en centimes.

| Phase | Description | Diff |
|---|---|---|
| **P10.3.1** | Service `debts/service/remaining.py` : requête SQL `SELECT amount_cents - COALESCE(SUM(sl.amount_cents), 0) FROM debts LEFT JOIN settlement_lines sl ON sl.debt_id = debts.id WHERE debts.id = :id GROUP BY debts.id, debts.amount_cents`. Helper `list_open_debts_between(user_a, user_b) → list[(Debt, remaining)]`. Tests intégration | ~150 |
| **P10.3.2** | Étendre `list_debts_for_user` (E09) pour inclure le `remaining_cents` calculé. Tests : dette de 50€ + settlement_line 30 = remaining 20 | ~100 |

---

### S10.4 — Routes settlements

| Phase | Description | Diff |
|---|---|---|
| **P10.4.1** | Schemas + route `POST /settlements` (créer settlement) + `GET /settlements?with_user=…` (lister settlements d'un user avec une contrepartie). RBAC : le user doit être impliqué dans toutes les dettes apurées (créancier ou débiteur). Tests httpx | ~200 |
| **P10.4.2** | Route `GET /settlements/{id}` détaillé (avec les SettlementLine et les Debt référencées). Tests | ~100 |

---

### S10.5 — Hypothesis : conservation du solde net

**Livrable observable** : property test passe.

| Phase | Description | Diff |
|---|---|---|
| **P10.5.1** | Strategy `debt_settlement_scenario_strategy` : génère un set de dettes entre 2 users + un set de settlements qui les apurent (somme nette = 0). Property : `sum(remaining_cents of debts between A and B) == 0` après apurement complet | ~180 |
| **P10.5.2** | Property additionnelle : pour tout settlement valide, `compute_remaining` de toutes les dettes apurées ≥ 0 (aucun over-settlement). Si une SettlementLine tente d'apurer plus que `remaining` → validation refuse | ~120 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S10.1 (2 phases) | Modèles | 200 | 200 |
| S10.2 (2 phases) | Validation domain + service | 450 | 650 |
| S10.3 (2 phases) | Calcul solde restant | 250 | 900 |
| S10.4 (2 phases) | Routes | 300 | 1200 |
| S10.5 (2 phases) | Hypothesis | 300 | 1500 |
| **Total** | **5 stories / 10 phases** | **~1500 lignes** | |

---

## Critères d'acceptation

- [ ] `Settlement` non-virtuel : `sum(SettlementLine.amount) == linked_tx.amount` (validation refuse sinon)
- [ ] Toutes les `debt_id` d'un `Settlement` concernent les 2 mêmes contreparties (rejet sinon)
- [ ] Solde restant d'une `Debt` = `amount - sum(settlement_lines)`, jamais matérialisé en colonne
- [ ] `linked_transaction_id` NULL ssi `type == 'virtual'`
- [ ] Property Hypothesis : conservation du solde net après apurement complet
- [ ] Property Hypothesis : aucun over-settlement possible
- [ ] Coverage `debts/domain.py` (Settlement) ≥ 90%, service ≥ 80%

---

## Notes pour l'implémenteur

- Le `Settlement.type == 'internal_transfer'` exige que `linked_transaction_id` pointe vers une `Transaction` confirmed qui est un transfert intra-foyer (deux splits sur deux comptes du foyer, montants opposés). Validation à ajouter au `SettlementValidator`.
- `external_transfer` : la `Transaction` source a un split sortant et un split sur une catégorie "Transfert vers tiers" ou similaire (non-foyer). À documenter dans le runbook utilisateur.
- Les `SettlementLine.amount_cents` peuvent être négatifs pour les dettes en sens inverse (nettage cross-direction). Le validateur doit calculer la somme algébrique alignée sur le sens du virement.
- La suggestion UX automatique des dettes à netter est repoussée en V2 (cf. Q16). En E10, l'utilisateur sélectionne manuellement les dettes à apurer dans son UI.
- E11 (overflow F10) bénéficiera des helpers `compute_remaining` et `list_open_debts_between` — anticiper leur signature utilisable.
