# E06 — Categories hiérarchiques

> **Durée estimée** : 3-4 jours
> **Statut** : not started
> **Dépend de** : E05
> **Bloque** : E07 (transactions référencent catégories), E08 (budgets posés sur catégories)
> **ADRs activés** : aucun (les arbitrages F08 sont dans CONTEXT.md)

---

## Objectif

Implémenter F08 partie 1 : catégories arborescentes illimitées en profondeur, cycle prevention au service, archivage soft-delete, réorganisation libre avec agrégats rétroactifs assumés. Synchronisée au foyer (bucket `household` mais sync activé seulement à E13).

Livrable agrégé : un user peut créer une hiérarchie de catégories aussi profonde qu'il veut, déplacer un sous-arbre, archiver une catégorie utilisée (avec interdiction de hard-delete si elle a des références).

---

## Stories

### S06.1 — Modèle `Category` + migration

**Livrable observable** : table `categories` créée avec self-FK + index parent.

| Phase | Description | Diff |
|---|---|---|
| **P06.1.1** | Modèle `Category` dans `modules/budget/models.py` (les categories vivent dans budget côté code car elles sont quasi-exclusivement utilisées par les budgets et transactions) : `id`, `name`, `color` (hex), `icon` (text), `parent_id` FK NULL self, `created_at`, `archived_at` NULL. Pas de constraint cycle SQL (vérifié au service) | ~80 |
| **P06.1.2** | Migration `0008_categories.py` + index sur `parent_id` + index partial `WHERE archived_at IS NULL` (les listings excluent archivées). Test niveau 1 schema check | ~100 |

---

### S06.2 — Cycle prevention au service

**Livrable observable** : tentative de créer un cycle `A → B → A` échoue avec `CategoryCycleError`.

| Phase | Description | Diff |
|---|---|---|
| **P06.2.1** | `budget/domain.py` (oui le module budget porte aussi les categories) : `CycleDetector` pur : `walk_up_parents(start_id, would_become_child_of) → raises CategoryCycleError if would_create_cycle`. Tests example + Hypothesis (gen arbres aléatoires, vérifie qu'aucune mutation acceptée ne crée de cycle) | ~150 |
| **P06.2.2** | `budget.service.create_category` et `move_category` (déplacement) appellent `CycleDetector` **avant tout write** (flush-only, ADR 0015). Tests intégration : arbre A → B → C ; mettre A enfant de C échoue (`CategoryCycleError`) ; **mettre A enfant de B (B déjà enfant de A) échoue aussi** — déplacer un nœud sous l'un de ses propres descendants (direct ou indirect) = cycle ; déplacer C sous A (non-descendant de C) → accepté | ~120 |

---

### S06.3 — Archive (soft-delete) + interdiction hard-delete

**Livrable observable** : `DELETE /categories/{id}` archive ; tentative de hard-delete via SQL direct n'est pas exposée mais le code service refuse si la catégorie a des sous-catégories ou transactions.

| Phase | Description | Diff |
|---|---|---|
| **P06.3.1** | `budget.service.archive_category(id)` : set `archived_at = now()`. Pas de cascade. Tests | ~80 |
| **P06.3.2** | `budget.service.delete_category(id)` (hard) : compte sous-catégories + transactions qui référencent (via `splits.category_id`, mais splits n'existe pas encore — interdire si > 0 sous-cats pour l'instant, étendre à splits dans E07). Lève `CategoryInUseError`. Recommandation utilisateur : utiliser archive plutôt. Tests | ~100 |
| **P06.3.3** | Routes `POST /categories`, `GET /categories?include_archived=false`, `PATCH /categories/{id}` (édition name/color/icon), `PATCH /categories/{id}/parent` (déplacement), `DELETE /categories/{id}` (archive). Audit log du déplacement. Tests httpx | ~200 |

---

### S06.4 — Hypothesis : invariants hiérarchie

**Livrable observable** : `tests/strategies.py` expose `category_tree_strategy` (arbre acyclique par construction, paramétrable — réuse E07/E08) ; les properties Hypothesis sur l'acyclicité post-mutation (domaine pur `CycleDetector`) et la non-cascade / non-re-parentage de l'archivage (`archive_category`, testcontainers) passent en CI et **échouent** si une règle S06.2/S06.3 régresse.

> Périmètre réel (vs ébauche initiale) : l'**idempotence de l'archivage** est déjà verrouillée par l'example `test_archive_already_archived_returns_false` (S06.3) — re-property = doublon. La **stabilité des agrégats lors d'un déplacement** est reportée à E08 (aucun agrégat n'existe en E06 ; les `Budget` arrivent en E08).

| Phase | Description | Diff |
|---|---|---|
| **P06.4.1** | `category_tree_strategy` + `GeneratedCategoryTree` dans `tests/strategies.py` (acyclique par construction, paramétrable taille/profondeur/arité). Property (a) cohérence strategy↔`CycleDetector`. Property (b) acyclicité post-mutation (oracle DFS **indépendant**, rebranche l'inline S06.2). Property (c) archivage sans cascade **ni** re-parentage (service + testcontainers). Aucune Hypothesis sur HTTP | ~120 |

---

### S06.5 — Parcours E2E API : cycle de vie d'une hiérarchie de catégories

**Livrable observable** : `tests/e2e/test_category_hierarchy_lifecycle.py` (Parcours 3 du tier E2E API, §6.3) vert en CI — une chaîne HTTP boîte-noire unique sur `committed_client` (FastAPI réel + Postgres testcontainers) du point de vue d'un client qui ne connaît que l'API publique.

Ce parcours **anticipe au niveau API** la couverture E06 des 5 parcours Playwright finaux (§6.2). Comme les Parcours 1/2 existants (issue #90), il asserte des **transitions d'état et de la propagation inter-modules** (REST → domaine → audit), **jamais** les contrats d'endpoint déjà couverts par les tests d'intégration de S06.3 (garde-fou anti-duplication §12).

| Phase | Description | Diff |
|---|---|---|
| **P06.5.1** | `tests/e2e/test_category_hierarchy_lifecycle.py` + helpers `create_category` et `fetch_audit_by_action` (projection side-channel `(actor, target, event_metadata)` filtrée par action — robuste aux rows `invite_*` qu'insère `onboard_member`) dans `tests/e2e/_helpers.py`. Chaîne : `bootstrap_admin` → construction d'un arbre `A › B › C` via `POST /categories` → **cycle indirect refusé** (`PATCH /categories/A/parent {parent_id: C}` → 4xx `CategoryCycleError`, arbre inchangé vérifié par `GET` **et** aucune row d'audit — moitié négative de l'oracle) → **archivage sans cascade** (`DELETE /categories/B` → 204 ; B a alors un parent A **et** un enfant C, tous deux restent actifs, C non re-parenté — non-cascade ascendante+descendante, vérifié bout-en-bout) → **filtre listing** (`GET /categories?include_archived=false` exclut B ; `=true` la réinclut avec `archived_at` non-null) → **déplacement légitime** (`PATCH /categories/C/parent {parent_id: A}` → 200) avec assertion **side-channel** (D3) de l'audit `CATEGORY_MOVED` (`from_parent_id=B`, `to_parent_id=A`, `by=admin`, `target NULL`) — la paire move+audit dans une **même transaction** (D5/D6) → **étanchéité household-scope** : un membre non-admin onboardé (`onboard_member`) crée/déplace aussi des catégories (pas de filtre personnel — distinct de l'étanchéité comptes F03), l'admin voit la catégorie du membre dans le listing, et le move du membre est audité sous son propre actor. Le hard-delete (`CategoryInUseError`) n'est **pas exposé en HTTP** (DELETE = archive) ⇒ hors périmètre, reste couvert au service/intégration (S06.3) | ~195 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S06.1 (2 phases) | Modèle + migration | 180 | 180 |
| S06.2 (2 phases) | Cycle prevention | 270 | 450 |
| S06.3 (3 phases) | Archive + routes | 380 | 830 |
| S06.4 (1 phase) | Hypothesis | 120 | 950 |
| S06.5 (1 phase) | Parcours E2E API | 195 | 1145 |
| **Total** | **5 stories / 9 phases** | **~1145 lignes** | |

---

## Critères d'acceptation

- [ ] Création de cycle A→B→A échoue avec `CategoryCycleError`
- [ ] Création de cycle indirect (déplacer un parent dans un de ses descendants) échoue
- [ ] Archive d'une catégorie set `archived_at`, ne touche pas aux enfants
- [ ] Hard-delete d'une catégorie avec sous-catégories échoue avec `CategoryInUseError`
- [ ] `GET /categories?include_archived=false` exclut les archivées (défaut)
- [ ] Déplacement d'un sous-arbre laisse un audit log
- [ ] Property Hypothesis : toute mutation acceptée laisse l'arbre acyclique
- [ ] Coverage `budget/domain.py` ≥ 90% (partie CycleDetector)
- [ ] Parcours E2E API (S06.5) vert en CI : cycle indirect refusé → déplacement audité (`CATEGORY_MOVED` side-channel) → archivage sans cascade → filtre `include_archived` → étanchéité household-scope (membre non-admin)

---

## Notes pour l'implémenteur

- Les categories ne sont **pas encore syncs** en E06 — la sync rule `household` bucket sera activée en E13. Pour l'instant, REST seulement.
- Le déplacement (`PATCH /categories/{id}/parent`) est une opération sensible (les agrégats budget remontent automatiquement dans la nouvelle hiérarchie). Audit log obligatoire avec `from_parent`, `to_parent`, `by_user`. Pas de confirmation utilisateur (UI affiche un warning ; décision finale en UI).
- `CycleDetector` est en `domain.py` (pur, testable sans DB). Le service injecte la fonction de lookup parent (qui touche la DB). Inversion de dépendance simple.
- La constance "infinie en profondeur" tient en pratique tant que `walk_up_parents` reste linéaire. Un hard cap UI à 10 niveaux affichables est une décision UX, pas domaine.
