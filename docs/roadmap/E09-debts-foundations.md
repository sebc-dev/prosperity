# E09 — Debts foundations (projection + share_request)

> **Durée estimée** : 5-7 jours
> **Statut** : not started
> **Dépend de** : E05, E07
> **Bloque** : E10, E11
> **ADRs activés** : 0002 (debts projection serveur), 0003 (column-level filter pour `source_transaction_id`)

---

## Objectif

Implémenter F09 partie 1 dans sa version MVP : `Debt` comme **projection serveur** (table matérialisée, lecture seule côté client via sync rules) + `ShareRequest` (acte explicite depuis compte personnel) + dashboard "mes dettes par contrepartie". Pas encore d'overflow F10 (E11) ni de Settlement (E10).

Livrable agrégé : Alice fait une dépense depuis son compte personnel → elle crée un `ShareRequest` (libellé court) → une `Debt` est matérialisée d'origine `personal_share_request` → Bob voit la dette dans son dashboard sans accès à la transaction source.

---

## Stories

### S09.1 — Modèles `Debt` + `ShareRequest`

**Livrable observable** : tables créées, migration passe, factories minimales.

| Phase | Description | Diff |
|---|---|---|
| **P09.1.1** | Modèle `Debt` dans `modules/debts/models.py` : `id`, `from_user_id`, `to_user_id`, `amount_cents`, `currency`, `account_id` FK (du compte source), `source_transaction_id` FK (vers transactions), `origin` Literal['shared_account_overflow','personal_share_request'], `share_ratio` Decimal(5,4) default 1.0, `created_at`, `materialized_by_calc_run` text (id du calc run pour debug). Index `(from_user_id)`, `(to_user_id)`, `(source_transaction_id)` | ~100 |
| **P09.1.2** | Modèle `ShareRequest` : `id`, `source_transaction_id` FK (unique partial WHERE active), `requested_by` FK (= owner du compte source), `requested_from` FK (user débiteur), `ratio` Decimal(5,4), `short_label` text (≤ 100 chars), `created_at`, `revoked_at` NULL. Unique `(source_transaction_id, requested_from) WHERE revoked_at IS NULL` | ~100 |
| **P09.1.3** | Migration `0011_debts_and_share_requests.py`. Test niveau 1 schema check | ~100 |

---

### S09.2 — `DebtCalculator` (domain pur)

**Livrable observable** : fonction pure `DebtCalculator.compute_for_share_request(share_request, transaction) → list[Debt]` testable sans DB.

| Phase | Description | Diff |
|---|---|---|
| **P09.2.1** | `modules/debts/domain.py` : Pydantic `Debt` du domain (mirror du modèle SQLA mais pur). `DebtCalculator` avec méthode `compute_for_share_request` qui prend un `ShareRequest` + la `Transaction` source + son owner, retourne une liste de `Debt` (typiquement 1 : `requested_from → requested_by` du montant `tx.total × ratio`). Tests example | ~150 |
| **P09.2.2** | Property Hypothesis : `compute_for_share_request` est **déterministe** (mêmes inputs → mêmes outputs) ; **antisymétrique sur la direction** (si on inversait `requested_by` et `requested_from`, le sign de la dette s'inverserait, mais nous ne testons pas cet inverse réel — juste que la fonction respecte la direction donnée). Idempotence : appliquer 2x → même set | ~120 |

---

### S09.3 — Service share_request + matérialisation

**Livrable observable** : `debts.public.create_share_request(...)` crée la `ShareRequest`, matérialise la `Debt`, dans une transaction DB unique.

| Phase | Description | Diff |
|---|---|---|
| **P09.3.1** | Service `debts/service/share_request.py` : `create_share_request(transaction_id, requested_from, ratio, short_label, by_user_id)`. Vérifie : (i) `by_user_id` est owner du compte source, (ii) compte source est personnel (pas commun), (iii) `requested_from ≠ requested_by`, (iv) ratio valide (0 < ratio ≤ 1), (v) une `ShareRequest` active n'existe pas déjà pour cette paire `(tx, requested_from)`. En transaction DB : insert `ShareRequest` + matérialise `Debt` via `DebtCalculator` + insert. Tests intégration | ~250 |
| **P09.3.2** | `revoke_share_request(share_request_id, by_user_id)` : vérifie que `by_user_id` est `requested_by`. Set `revoked_at`. **Supprime la `Debt` matérialisée** (no audit on Debt — la trace vit dans ShareRequest). Tests | ~120 |
| **P09.3.3** | Route `POST /transactions/{tx_id}/share-requests` (crée) + `DELETE /share-requests/{id}` (révoque). Schemas Pydantic + tests httpx | ~180 |

---

### S09.4 — Dashboard dettes

**Livrable observable** : `GET /debts` retourne les dettes du user (créancier ou débiteur) avec contrepartie agrégée.

| Phase | Description | Diff |
|---|---|---|
| **P09.4.1** | `debts.public.list_debts_for_user(user_id) → list[DebtWithContext]` : enrichit avec le `short_label` du ShareRequest (pour `personal_share_request`) et masque le `source_transaction_id` si user_id ≠ owner du compte source (cohérent avec future column-level filter sync rule ADR 0003). Tests intégration | ~180 |
| **P09.4.2** | Route `GET /debts?direction=all|owed_to_me|owed_by_me&with=user_id`. Tests httpx | ~150 |
| **P09.4.3** | Route `GET /debts/by-counterparty` : agrégation par contrepartie (`{user_id, net_amount, debts_count}`). Pour V2 nettage UX, mais utile dès V1 pour le dashboard. Tests | ~120 |

---

### S09.5 — Hypothesis : invariants debts

| Phase | Description | Diff |
|---|---|---|
| **P09.5.1** | Strategies `share_request_strategy`, `debt_strategy`. Properties : (1) `create_share_request` + `revoke_share_request` = état initial (matérialisation/dématérialisation symétriques) ; (2) deux `create_share_request` consécutifs sur la même paire échouent (idempotence partial unique) ; (3) jamais d'auto-dette (`from_user_id == to_user_id` impossible) | ~150 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S09.1 (3 phases) | Modèles + migration | 300 | 300 |
| S09.2 (2 phases) | DebtCalculator domain | 270 | 570 |
| S09.3 (3 phases) | Service share_request | 550 | 1120 |
| S09.4 (3 phases) | Dashboard | 450 | 1570 |
| S09.5 (1 phase) | Hypothesis | 150 | 1720 |
| **Total** | **5 stories / 12 phases** | **~1720 lignes** | |

---

## Critères d'acceptation

- [ ] `ShareRequest` ne peut être créée que par l'owner d'un compte **personnel**
- [ ] `ShareRequest` active unique par paire `(tx, requested_from)`
- [ ] `Debt` matérialisée d'origine `personal_share_request` avec `source_transaction_id` pointant vers la transaction source
- [ ] `list_debts_for_user` retourne le `short_label` mais masque `source_transaction_id` si user ≠ owner compte source
- [ ] Route `GET /debts/by-counterparty` agrège correctement net amount
- [ ] Property Hypothesis : 3 invariants documentés passent
- [ ] Coverage `debts/domain.py` ≥ 90%, service ≥ 75%

---

## Notes pour l'implémenteur

- La `Debt` est **projection** : aucune route HTTP `POST /debts` ou `PATCH /debts/amount`. Seul `share_ratio` sera éditable plus tard via `PATCH /debts/{id}/share-ratio` (E10 ou E11). En MVP E09, pas de mutation `Debt` côté client.
- `revoke_share_request` supprime la `Debt` matérialisée. Pas de soft-delete sur `Debt` parce qu'elle est régénérable à tout moment depuis `ShareRequest` (idempotent).
- Le masquage de `source_transaction_id` côté API est fait **à la lecture**. Le champ reste en DB (debt complet côté serveur). Le filtre serveur évite la fuite via API REST ; le sync rule PowerSync (E13) ajoutera la même garantie côté sync.
- Le `materialized_by_calc_run` est un identifiant texte du calc run (timestamp+pid) utile pour debug "pourquoi cette dette existe-t-elle". Non requis fonctionnellement mais bénéfice forensique élevé.
