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
| **P06.2.2** | `budget.service.create_category` et `update_category_parent` appellent `CycleDetector`. Tests intégration : créer A → B → C; tenter de mettre A en enfant de C échoue avec `CategoryCycleError` ; mettre A en enfant de B (pas un cycle car B est enfant de A initialement) → on doit accepter ? Cas tricky : déplacer un parent dans son propre enfant = cycle. Test explicite | ~120 |

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

**Livrable observable** : property tests sur l'absence de cycle, l'idempotence de l'archivage, la stabilité des agrégats lors d'un déplacement.

| Phase | Description | Diff |
|---|---|---|
| **P06.4.1** | Strategy `category_tree_strategy` : génère un arbre N-aire random valide (sans cycle). Property : toute mutation `parent_id` qui passe la validation produit toujours un arbre valide. Property : archiver une catégorie n'affecte pas ses enfants (pas de cascade) | ~120 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S06.1 (2 phases) | Modèle + migration | 180 | 180 |
| S06.2 (2 phases) | Cycle prevention | 270 | 450 |
| S06.3 (3 phases) | Archive + routes | 380 | 830 |
| S06.4 (1 phase) | Hypothesis | 120 | 950 |
| **Total** | **4 stories / 8 phases** | **~950 lignes** | |

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

---

## Notes pour l'implémenteur

- Les categories ne sont **pas encore syncs** en E06 — la sync rule `household` bucket sera activée en E13. Pour l'instant, REST seulement.
- Le déplacement (`PATCH /categories/{id}/parent`) est une opération sensible (les agrégats budget remontent automatiquement dans la nouvelle hiérarchie). Audit log obligatoire avec `from_parent`, `to_parent`, `by_user`. Pas de confirmation utilisateur (UI affiche un warning ; décision finale en UI).
- `CycleDetector` est en `domain.py` (pur, testable sans DB). Le service injecte la fonction de lookup parent (qui touche la DB). Inversion de dépendance simple.
- La constance "infinie en profondeur" tient en pratique tant que `walk_up_parents` reste linéaire. Un hard cap UI à 10 niveaux affichables est une décision UX, pas domaine.
