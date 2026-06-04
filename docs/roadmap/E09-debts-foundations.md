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
| **P09.1.1** | Modèle `Debt` dans `modules/debts/models.py` : `id`, `from_user_id`, `to_user_id`, `amount_cents`, `currency`, `account_id` FK (du compte source), `source_transaction_id` FK (vers transactions), `origin` Literal['shared_account_overflow','personal_share_request'], `share_ratio` Decimal(5,4) default 1.0, `created_at`, `materialization_trace` text (marqueur forensique server-only — **jamais exposé via API**, cf. note infra). Index `(from_user_id)`, `(to_user_id)`, `(source_transaction_id)`. **CHECK défensifs** (transforment les invariants testés en garanties DB) : `ck_debts_no_self_debt` (`from_user_id <> to_user_id`, cf. property S09.5-3) et `ck_debts_amount_positive` (`amount_cents > 0`, garde-fou montant nul/négatif). | ~110 |
| **P09.1.2** | Modèle `ShareRequest` : `id`, `source_transaction_id` FK (unique partial WHERE active), `requested_by` FK (= owner du compte source), `requested_from` FK (user débiteur), `ratio` Decimal(5,4), `short_label` text (≤ 100 chars, **validation serveur** : trim + rejet caractères de contrôle, cf. S09.3), `created_at`, `revoked_at` NULL. Unique `(source_transaction_id, requested_from) WHERE revoked_at IS NULL`. CHECK `ck_share_requests_no_self` (`requested_by <> requested_from`). | ~100 |
| **P09.1.3** | Migration `0014_debts_and_share_requests.py` (`down_revision = "0013"`). **Ordre** : (1) `create_table('share_requests')` (avec sa FK `source_transaction_id → transactions.id`) ; (2) `create_table('debts')` ; (3) `op.create_foreign_key` activant la FK dormante `transactions.share_request_id → share_requests.id` — colonne **déjà posée nullable en `0010`/S07.4**, donc **pas de `add_column`**, juste la contrainte. La FK `transactions ↔ share_requests` est circulaire mais les deux colonnes sont nullable → création sans cycle bloquant. **`ON DELETE`** : `debts.source_transaction_id` et `share_requests.source_transaction_id` en `CASCADE` (supprimer/void une tx source nettoie sa projection) ; `debts.account_id` en `RESTRICT` ; `transactions.share_request_id → share_requests.id` en `SET NULL`. La révocation ne supprime pas la SR (set `revoked_at`, S09.3) → `transactions.share_request_id` reste pointé sur une SR `revoked`, c'est voulu (la tx garde la trace du lien). Scission import-linter `2-debts` (premières internals de `debts`, cf. note infra). Mettre à jour le **snapshot SQL de référence** (test niveau 1) pour inclure les deux tables **et** l'activation de la FK dormante. Test niveau 1 schema check. | ~130 |

---

### S09.2 — `DebtCalculator` (domain pur)

**Livrable observable** : fonction pure `DebtCalculator.compute_for_share_request(*, share_request: ShareRequestData, expense_total: Money, source_account_id) → list[Debt]` testable sans DB ni import du type `Transaction` (les scalaires `requested_by`/`requested_from`/`ratio`/`source_transaction_id`/`short_label` voyagent dans `ShareRequestData` ; la devise voyage dans `Money` — cf. issue #143 P09.2.1, qui fait autorité sur la signature à plat de ce tableau). **TDD strict** : les tests du calculator précèdent l'implémentation (red → green, §2.3 stratégie).

> **Signature & ADR 0002.** L'ADR 0002 décrit le `DebtCalculator` comme `(Transaction, Budget, Account) → list[Debt]`. E09 **affine** ce contrat (cf. note « Refined-by » ajoutée à l'ADR 0002) : pour garder `debts.domain` strictement pur (pas d'import du type `Transaction`, conforme au graphe ADR 0005), le calculator reçoit des **scalaires** (`expense_total` calculé par le service) plutôt que l'agrégat. `compute_for_share_request` n'est **qu'une** méthode du calculator — le sous-cas `personal_share_request` ; le sous-cas `shared_account_overflow` (`compute_for_overflow`, qui consommera l'argument `Budget` de la signature ADR) est **déféré à E11**.

| Phase | Description | Diff |
|---|---|---|
| **P09.2.1** | `modules/debts/domain.py` : Pydantic `Debt` du domain (mirror du modèle SQLA mais pur). `DebtCalculator.compute_for_share_request` reçoit des **scalaires purs** (`from_user_id`, `to_user_id`, `expense_total`, `ratio`, `account_id`, `currency`, `source_transaction_id`) — **aucun import du type `Transaction`** — et retourne une liste de `Debt` (typiquement 1 : `from_user_id=requested_from → to_user_id=requested_by`, montant `expense_total × ratio`). La dérivation `expense_total` = somme des **classification legs** de la tx (ADR 0017/E08.5, **pas** la funding leg) est faite par le **service** (S09.3) qui passe le scalaire au calculator → cette dérivation est testée en **intégration** (S09.3), pas ici (évite le doublon unitaire/intégration, §12). Garde-fou domaine : le calculator rejette `expense_total ≤ 0` et `from == to`. Tests example (TDD). | ~150 |
| **P09.2.2** | Property Hypothesis (domaine pur, sans DB) : (a) **déterminisme** (mêmes inputs → mêmes outputs) ; (b) **antisymétrie de direction réelle et quantifiable** — `compute_for_share_request(from=A, to=B, …)` produit une `Debt` dont le montant orienté est l'**opposé** de `compute_for_share_request(from=B, to=A, …)` (invariant `debt(A→B) == −debt(B→A)`, cf. Stratégie §82) ; (c) **idempotence** : appliquer 2× → même set. `@example()` pour épingler ratio aux bornes (`→0⁺`, `=1`). | ~120 |

---

### S09.3 — Service share_request + matérialisation

**Livrable observable** : `debts.public.create_share_request(...)` crée la `ShareRequest`, matérialise la `Debt`, dans une transaction DB unique.

| Phase | Description | Diff |
|---|---|---|
| **P09.3.1** | Service `debts/service/share_request.py` : `create_share_request(transaction_id, requested_from, ratio, short_label, by_user_id)`. **Ordre des vérifs (404 d'abord pour ne pas faire oracle, cf. note sécurité)** : (i) tx source **accessible & existante** pour `by_user_id` → sinon **404 uniforme** (même réponse pour « inexistante » et « pas la tienne », gabarit `transactions/transports/http.py`) ; (ii) `by_user_id` est owner du compte source **et** compte source **personnel** — les deux en **un seul appel** `accounts.public.owned_personal_account_ids(by_user_id)` (réutilise l'helper existant, déjà consommé par budget) ; (iii) **tx source `confirmed`** (ADR 0001 : splits/montant gelés → `expense_total` figé, élimine la staleness, cf. note infra) ; (iv) `requested_from` est un **membre du foyer existant** (sinon dette fantôme ; réponse 422/404 indistincte) ; (v) `requested_from ≠ requested_by` ; (vi) ratio valide (`0 < ratio ≤ 1`) ; (vii) `short_label` validé (Pydantic : longueur ≤ 100, trim, rejet caractères de contrôle) ; (viii) `expense_total > 0` (dérivé = somme des **classification legs**, funding leg exclue) ; (ix) pas de `ShareRequest` active pour la paire `(tx, requested_from)`. En transaction DB unique (commit par `get_db`, ADR 0015) : insert `ShareRequest` + dérive `expense_total` + matérialise `Debt` via `DebtCalculator` + insert. Tests intégration (dont la **dérivation `expense_total`** : tx funding leg + N classification legs → assert funding exclue ; + un test négatif par vérif (i)…(ix)). | ~270 |
| **P09.3.2** | `revoke_share_request(share_request_id, by_user_id)` : vérifie que `by_user_id` est `requested_by` → sinon **404 uniforme** (ne pas confirmer l'existence d'une SR d'autrui). Set `revoked_at`. **Supprime la `Debt` matérialisée** (hard-delete ; no audit on Debt — la trace vit dans `ShareRequest.revoked_at` ; **non auditable admin**, ≠ S04.2). Idempotence : re-revoke d'une SR déjà révoquée = no-op (pas de crash, pas de recréation). Tests (révocation OK, par non-`requested_by` → 404, double revoke). | ~130 |
| **P09.3.3** | Route `POST /transactions/{tx_id}/share-requests` (crée) + `DELETE /share-requests/{id}` (révoque). Schemas Pydantic (le schema de `short_label` porte la validation longueur/trim/contrôle). **`requested_from` & périmètre dérivés du token** (`by_user_id = current_user.id`, jamais du body — D6). import-linter : ajout des `ignore_imports` second-hop réellement présents (`auth.public → auth.X`, `accounts.public → accounts.X`, et `transactions.public → transactions.X` **uniquement pour les arcs effectivement importés** — sinon `unmatched_ignore_imports_alerting = error` casse le lint ; cf. note infra). Schemas Pydantic + tests httpx. | ~180 |

---

### S09.4 — Dashboard dettes

**Livrable observable** : `GET /debts` retourne les dettes du user (créancier ou débiteur) avec contrepartie agrégée. **Périmètre toujours dérivé du token** (jamais un `user_id` du body/query).

| Phase | Description | Diff |
|---|---|---|
| **P09.4.1** | `debts.public.list_debts_for_user(user_id) → list[DebtWithContext]` (le `user_id` est **imposé par l'appelant = token**, pas un sélecteur de propriétaire). **DTO en allowlist** : `DebtWithContext` n'expose qu'un set explicite de champs ; **jamais** `materialization_trace`. Pour le **débiteur** (lecteur ≠ owner du compte source, c.-à-d. `user_id ≠ to_user_id` pour `personal_share_request` — pas besoin d'un helper accounts, l'owner = `requested_by` = `to_user_id`), masquer **`source_transaction_id` ET `account_id`** (le compte personnel source ne doit pas fuiter, glossaire §97-98/§272 ; cohérent avec la future column-level filter sync rule ADR 0003). **Enrichissement à la lecture, côté serveur** (qui a l'accès complet) : `short_label` (du `ShareRequest`) + `category`/`date` **par join sur la transaction source** (le serveur lit la tx, ne renvoie que `category`/`date` au débiteur — `category_id` restant éditable après confirmed, le join garde la valeur **fraîche** plutôt que de la dénormaliser/figer). Le masquage + l'allowlist sont **centralisés** dans un helper unique réutilisé par P09.4.2 **et** P09.4.3. Tests intégration **dont test de non-fuite** : en tant que débiteur → `source_transaction_id`/`account_id`/`materialization_trace` absents du payload ; en tant qu'owner → `source_transaction_id`/`account_id` présents. | ~210 |
| **P09.4.2** | Route `GET /debts?direction=all|owed_to_me|owed_by_me&with=user_id`. `with` = **filtre de contrepartie appliqué APRÈS le bornage au token** (dettes où le caller est créancier OU débiteur ET la contrepartie == `with`) — **jamais** un sélecteur de propriétaire. Tests httpx (dont test négatif IDOR : caller A ne voit aucune dette d'un tiers via `with`). | ~150 |
| **P09.4.3** | Route `GET /debts/by-counterparty` : agrégation par contrepartie (`{user_id, net_amount, debts_count}`). Pour V2 nettage UX, mais utile dès V1 pour le dashboard. **Passe par le même helper centralisé de bornage/masquage que P09.4.1** (jamais de chemin de lecture parallèle) — borné au token, n'expose aucun champ source. Tests (dont assert qu'aucun champ source ne fuite via l'agrégat). | ~120 |

---

### S09.5 — Hypothesis : invariants debts

| Phase | Description | Diff |
|---|---|---|
| **P09.5.1** | Strategies `share_request_strategy`, `debt_strategy`. **Hypothesis strictement sur le domaine pur** (§4.2 : pas d'Hypothesis sur les effets de bord/DB). Properties domaine sur le `DebtCalculator` : (1) **symétrie matérialisation/dématérialisation** au niveau `list[Debt]` (matérialiser puis « dé-matérialiser » = set vide), exprimée **sans DB** ; (3) jamais d'auto-dette (`from_user_id == to_user_id` impossible en sortie du calculator). **Reclassées en tests example-based d'intégration** (S09.3, pas Hypothesis) car effets de bord DB : (2) deux `create_share_request` consécutifs sur la même paire échouent (idempotence du partial unique) — Hypothesis + testcontainers serait lent/flaky (budget CI < 5 min). **Acté non testé ici** (§2.7) : l'invariant **zero-sum** sur les dettes d'une même tx d'origine (dégénéré en MVP `personal_share_request` à 1 dette ; testé en E10/E11 multi-débiteurs) ; la **staleness** de la `Debt` sur édition de la tx source (éliminée par l'exigence tx `confirmed`, cf. S09.3-iii). | ~150 |

> **Delta d'implémentation (issue #146, plan + re-review APPROVE).** Après implémentation de S09.1–S09.4, la décomposition ci-dessus a été affinée (le contexte courant prime, cf. guide d'authoring §3) : (a) en MVP `personal_share_request`, `compute_for_share_request` produit **exactement 1** dette, donc la « symétrie de projection au niveau `list[Debt]` » (1) est **tautologique** (§12) et la « non auto-dette » (3) **doublonne** `test_debts_domain.py` (S09.2) — l'espace des invariants pur-domaine du calculator est **clos par S09.2** ; (b) la part intégration a été **absorbée** par S09.1 (CASCADE FK, `test_debts_models.py`) et S09.3 (symétrie persistée `create↔revoke` + idempotence partial-unique, `test_share_request_service.py`). Le livrable réel de S09.5 est donc : l'**infrastructure Hypothesis réutilisable** (`distinct_uuid_pair`/`share_request_strategy`/`debt_strategy`, socle des properties zero-sum **non dégénérées** d'E10) + son **test de contrat** (`tests/unit/test_debts_invariants.py`) + **une consolidation CASCADE flux-réel** (`tests/integration/test_debts_invariants.py`, les deux projections du flux réel suivent leur tx en une suppression) + le **mapping AC → tests existants**. Aucune property cosmétique fabriquée pour « remplir » l'AC.

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S09.1 (3 phases) | Modèles + migration + CHECK | 340 | 340 |
| S09.2 (2 phases) | DebtCalculator domain | 270 | 610 |
| S09.3 (3 phases) | Service share_request | 580 | 1190 |
| S09.4 (3 phases) | Dashboard + masquage/allowlist | 480 | 1670 |
| S09.5 (1 phase) | Hypothesis | 150 | 1820 |
| **Total** | **5 stories / 12 phases** | **~1820 lignes** | |

---

## Critères d'acceptation

- [ ] `ShareRequest` créable uniquement par l'owner d'un compte **personnel**, sur une tx source **`confirmed`**, vers un `requested_from` **membre du foyer** ≠ `requested_by`
- [ ] `ShareRequest` active unique par paire `(tx, requested_from)`
- [ ] `Debt` matérialisée d'origine `personal_share_request` avec `source_transaction_id` ; `amount_cents = expense_total × ratio` où `expense_total` = somme des **classification legs** (funding leg exclue) ; CHECK DB `from <> to` et `amount_cents > 0`
- [ ] Périmètre de lecture **toujours dérivé du token** ; `with=user_id` = filtre de contrepartie post-bornage (pas d'IDOR) — test négatif inclus
- [ ] `DebtWithContext` en **allowlist** : expose `short_label` + `category`/`date` (join serveur), masque **`source_transaction_id` ET `account_id`** au débiteur (user ≠ owner compte source), n'expose **jamais** `materialization_trace` — test de non-fuite inclus
- [ ] `short_label` validé serveur (≤ 100, trim, rejet caractères de contrôle) ; rendu client échappé (documenté)
- [ ] 404 uniforme (jamais 403) sur tx/SR inaccessible ou inexistante
- [ ] `GET /debts/by-counterparty` agrège correctement net amount, via le même helper de bornage/masquage que `list_debts_for_user`
- [ ] Property Hypothesis (domaine pur) : déterminisme + antisymétrie `debt(A→B) == −debt(B→A)` + idempotence ; invariants symétrie & no-self-debt passent ; idempotence partial-unique testée en intégration
- [ ] Coverage `debts/domain.py` ≥ 90% lignes **+ ≥ 80% branches** ; service ≥ 75% lignes (avec un test négatif par vérif de `create_share_request`)

---

## Notes pour l'implémenteur

- La `Debt` est **projection** : aucune route HTTP `POST /debts` ou `PATCH /debts/amount`. Seul `share_ratio` sera éditable plus tard via `PATCH /debts/{id}/share-ratio` (E10 ou E11). En MVP E09, pas de mutation `Debt` côté client.
- `revoke_share_request` supprime la `Debt` matérialisée. Pas de soft-delete sur `Debt` parce qu'elle est régénérable à tout moment depuis `ShareRequest` (idempotent).
- **Masquage à la lecture, en allowlist.** `source_transaction_id` **et** `account_id` (compte personnel source) sont masqués au débiteur **à la lecture** ; `materialization_trace` n'est exposé à **personne**. Les champs restent en DB (debt complet côté serveur). Un **DTO en allowlist** (set explicite de champs) + le masquage sont **centralisés dans un helper unique** réutilisé par `/debts` et `/debts/by-counterparty` — pas de chemin de lecture parallèle qui ré-exposerait un champ. Le sync rule PowerSync (E13) ajoutera la même garantie (column-level filter, ADR 0003) côté sync.
- **`category`/`date` du débiteur = join serveur, pas dénormalisation.** Le débiteur a droit à `category`/`date` (glossaire §97-98/§272) mais pas à `source_transaction_id`. Le serveur (accès complet) les résout par **join sur la tx source** à la lecture et ne renvoie que `category`/`date`. On évite de dénormaliser `category_id`/`date` sur la `Debt` : `category_id` reste éditable après `confirmed`, le join garde la valeur **fraîche**.
- **Pas de staleness du montant.** `create_share_request` exige une tx source **`confirmed`** : sous ADR 0001, splits & montant sont gelés → `expense_total` est immuable → `Debt.amount_cents` ne dérive jamais. La re-matérialisation sur write de tx (chemin sync ADR 0002/0014, write upload handler) reste pertinente pour le sous-cas **overflow E11** (tx commun, budget mouvant) ; en E09 `personal_share_request` elle est inutile par construction.
- **`DebtCalculator` — divergence de signature assumée vs ADR 0002** (cf. note « Refined-by » ajoutée à l'ADR 0002) : domaine pur recevant des scalaires (`expense_total` calculé par le service) au lieu de `(Transaction, Budget, Account)` ; `compute_for_share_request` est la **méthode MVP**, `compute_for_overflow` (avec `Budget`) est **déférée E11**.
- Le `materialization_trace` (anciennement `materialized_by_calc_run`) est un marqueur texte **server-only** (horodatage) pour le forensique « pourquoi cette dette existe-t-elle ». En MVP il n'y a **pas** de calc run (insert one-shot synchrone) ; le champ **préfigure** l'id de calc run du mécanisme de matérialisation batch E11. **Jamais exposé via API** (hors allowlist DTO).
- **Items déférés explicites** : overflow F10 (`compute_for_overflow` + argument `Budget`) → E11 ; `Settlement`/`SettlementLine` → E10 ; `PATCH /debts/{id}/share-ratio` → E10/E11 ; sync rule PowerSync (column-level filter) → E13 ; re-matérialisation sur write de tx (chemin sync) → E11 ; invariant zero-sum multi-débiteurs → E10/E11.
- **Deltas appliqués à la création des issues (S09.1–S09.5, #142–#146)** :
  - **Migration** : `0011` est pris (budgets S08) — la migration debts est **`0014_debts_and_share_requests.py`** (`down_revision = "0013"`).
  - **FK dormante** : `transactions.share_request_id` posée nullable sans FK en `0010` (S07.4) ; `0014` active la FK `→ share_requests.id`. Lien au niveau DB uniquement (pas de relationship ORM cross-module).
  - **import-linter** : S09.1 donne ses premières internals à `debts` ⇒ contrat dédié **`2-debts`** (mirror **de la structure** de `2-transactions`, pas de sa liste d'arcs), `debts` retiré du `source_modules` du contrat `2`. Les `ignore_imports` second-hop sont ajoutés en S09.3 et **n'énumèrent que les arcs réellement importés** (`unmatched_ignore_imports_alerting = error` casse le lint sinon) : `auth.public → auth.X` (9 arcs, comme `2-accounts`), `accounts.public → accounts.X` (4 arcs) si `debts` consomme `accounts.public`, et `transactions.public → transactions.X` **uniquement** pour les arcs effectivement présents (à vérifier au moment de l'implémentation — il n'existe aucun précédent `transactions.public → transactions.internal` dans les contrats actuels). `debts` lit `transactions` via `.public` (couche inférieure dans le contrat 1, arc directionnel légitime).
  - **`expense_total` (ADR 0017/E08.5)** : le montant partageable = somme des **classification legs** (pas la funding leg) ; calculé par le service, passé au `DebtCalculator` pur.
