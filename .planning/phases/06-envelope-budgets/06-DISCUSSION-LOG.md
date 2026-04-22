# Phase 6: Envelope Budgets - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 06-envelope-budgets
**Areas discussed:** Liaison catégories, Visibilité sur compte partagé, Modèle d'allocation mensuelle, Calcul du consumed + workflow rollover

---

## Area Selection

**Question:** Quels axes veux-tu discuter pour Phase 6 — Envelope Budgets ?

| Option | Description | Selected |
|--------|-------------|----------|
| Liaison enveloppe ↔ catégories | CRITIQUE : l'entité Envelope n'a pas de champ category. Comment une enveloppe sait quelles transactions lui sont imputées ? | ✓ |
| Visibilité sur compte partagé | BLOCKER flaggé dans STATE.md : sur un compte commun, User A et User B voient-ils les mêmes enveloppes (SHARED) ou chacun a les siennes (PERSONAL) ? | ✓ |
| Modèle d'allocation mensuelle | Envelope a `budget` ET EnvelopeAllocation existe. Lequel fait autorité ? | ✓ |
| Calcul du consumed + workflow rollover | ENVL-03 : imputation auto. Calcul à la volée ou matérialisé ? Rollover automatique ou à la lecture ? | ✓ |

**User's choice:** Les 4 axes sélectionnés.

---

## Liaison catégories

### Question 1 : Comment une enveloppe sait quelles transactions lui appartiennent ?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 enveloppe = N catégories (Recommended) | Table de jonction N:N, contrainte : une catégorie ↔ 1 enveloppe par compte | ✓ |
| 1 enveloppe = 1 catégorie racine (inclut enfants) | Enveloppe liée à racine embrasse toutes les sous-catégories | |
| 1 enveloppe = 1 catégorie stricte | Mapping 1-à-1 | |
| Enveloppe sans catégorie (imputation manuelle) | L'utilisateur impute manuellement chaque transaction | |

**User's choice:** 1 enveloppe = N catégories (Recommended).
**Notes:** Flexibilité souhaitée pour grouper plusieurs catégories sous une enveloppe conceptuelle (ex: « Vie quotidienne »). → D-01.

### Question 2 : Si enveloppe liée à catégorie racine, les enfants y sont-elles imputées ?

| Option | Description | Selected |
|--------|-------------|----------|
| Oui, la racine embrasse les enfants (Recommended) | Lier 'Alimentation' impute tout sur 'Alimentation > Courses' et 'Alimentation > Restaurant' | ✓ |
| Non, liaison exacte uniquement | Il faut explicitement lier chaque catégorie | |

**User's choice:** Oui (Recommended). → D-02.

### Question 3 : Comment une transaction splittée (TXNS-06) impacte les enveloppes ?

| Option | Description | Selected |
|--------|-------------|----------|
| Chaque split impute son enveloppe au prorata (Recommended) | Un split 60€/40€ impacte 2 enveloppes séparément | ✓ |
| Ignoré (split hors scope envelope en v1) | Les transactions splittées ne sont pas imputées en Phase 6 | |

**User's choice:** Prorata (Recommended). → D-03.

### Question 4 : Transaction dont la catégorie n'est liée à AUCUNE enveloppe ?

| Option | Description | Selected |
|--------|-------------|----------|
| Ignorée silencieusement (Recommended) | Elle existe mais n'apparaît dans aucun solde | ✓ |
| Agrégée dans 'Hors budget' | Enveloppe implicite qui remonte dans le dashboard | |
| Warning affiché | UI signale 'N transactions non rattachées' | |

**User's choice:** Ignorée silencieusement (Recommended). → D-04.

---

## Partage

### Question 1 : Sur un compte COMMUN, comment cohabitent les enveloppes ?

| Option | Description | Selected |
|--------|-------------|----------|
| Enveloppes SHARED uniquement (Recommended) | Un compte commun = un budget commun, un seul set visible des deux users | ✓ |
| Mix libre : SHARED + PERSONAL | User A peut créer SHARED et PERSONAL sur le compte commun | |
| PERSONAL par défaut sur compte commun | Chaque user a ses propres enveloppes sur le compte commun | |

**User's choice:** SHARED uniquement (Recommended). Résout le blocker flaggé dans STATE.md. → D-05.

### Question 2 : Sur un compte PERSO, qui voit les enveloppes ?

| Option | Description | Selected |
|--------|-------------|----------|
| Seul l'owner du compte (Recommended) | Héritage naturel des permissions Phase 3 via AccountAccess | ✓ |
| Les users avec accès READ au compte | Partage READ → partage enveloppes | |

**User's choice:** Owner du compte (Recommended). → D-06.

**Corollaire (Claude's note):** Le scope de l'enveloppe sera dérivé du Account.accountType (AccountType enum PERSONAL/SHARED déjà existant), pas un choix utilisateur → D-07.

---

## Allocation

### Question 1 : Comment fonctionne le budget mensuel d'une enveloppe ?

| Option | Description | Selected |
|--------|-------------|----------|
| Budget fixe + overrides mensuels optionnels (Recommended) | Envelope.budget = défaut, EnvelopeAllocation override ponctuel | ✓ |
| Allocation par mois obligatoire | Supprimer Envelope.budget, forcer une allocation par mois | |
| Budget fixe uniquement (pas d'allocation variable en v1) | Envelope.budget seul, EnvelopeAllocation non utilisé | |

**User's choice:** Budget fixe + overrides (Recommended). → D-08.

### Question 2 : Que voit l'utilisateur à la création/édition d'une enveloppe ?

| Option | Description | Selected |
|--------|-------------|----------|
| Form simple : nom + catégories + budget + rollover (Recommended) | Overrides mensuels via action dédiée sur dashboard/liste | ✓ |
| Form complet avec tableau mensuel | 12 mois de l'année à éditer dès la création | |

**User's choice:** Form simple (Recommended). → D-09 et D-10.

---

## Consumed

### Question 1 : Comment est calculé le montant consommé d'une enveloppe ?

| Option | Description | Selected |
|--------|-------------|----------|
| À la volée : SUM SQL sur transactions (Recommended) | Aucun champ persisté, toujours cohérent | ✓ |
| Matérialisé : colonne consumed mise à jour au save | Meilleure performance lecture mais risque d'incohérence | |
| Cache applicatif (computed + invalidation) | Compromis mais complexité inutile à l'échelle d'un foyer | |

**User's choice:** À la volée (Recommended). → D-11.

### Question 2 : Quand le rollover (CARRY_OVER) est-il appliqué ?

| Option | Description | Selected |
|--------|-------------|----------|
| Calculé à la volée à la lecture (Recommended) | Pas de batch, toujours cohérent | ✓ |
| Job batch en fin de mois (cron) | Matérialisation via EnvelopeAllocation 'report' | |
| Manuel (bouton 'Reporter') | L'utilisateur clique pour reporter | |

**User's choice:** À la volée (Recommended). → D-12.

### Question 3 : Comment l'indicateur visuel (vert/jaune/rouge) est-il déclenché ?

| Option | Description | Selected |
|--------|-------------|----------|
| Vert <80%, Jaune 80-100%, Rouge >100% (Recommended) | Seuils codés en dur côté front | ✓ |
| Seuils configurables par enveloppe | 2 champs supplémentaires sur l'entité | |

**User's choice:** Seuils standards 80/100 (Recommended). → D-13.

### Question 4 : Où l'historique de consommation (ENVL-06) s'affiche-t-il ?

| Option | Description | Selected |
|--------|-------------|----------|
| Page dédiée envelope avec liste mensuelle (Recommended) | /envelopes/:id avec tableau 12 mois + graphique ngx-echarts optionnel | ✓ |
| Drawer / panel latéral dans la liste | Moins de routing mais espace limité | |
| Modal p-dialog avec onglets | Pattern établi mais mal adapté aux graphiques | |

**User's choice:** Page dédiée (Recommended). → D-14.

---

## Closing Question

**Question:** Reste-t-il des zones grises à explorer avant d'écrire CONTEXT.md ?

| Option | Description | Selected |
|--------|-------------|----------|
| Je suis prêt pour le contexte (Recommended) | Écrire CONTEXT.md avec les 12 décisions capturées | ✓ |
| Explorer d'autres zones grises | routing/nav, suppression enveloppe, compte archivé, filtres, endpoints REST | |

**User's choice:** Prêt pour le contexte. Les zones grises restantes (routing, suppression, archivage, filtres, endpoints) sont tranchées en Claude's Discretion dans CONTEXT.md ou dérivent des patterns des phases précédentes.

---

## Claude's Discretion

Les points suivants sont explicitement laissés à l'implémentation (recherche + planner) :
- Structure exacte des DTOs (records Java) et nommage des endpoints REST
- Récursion catégorie racine → enfants (CTE PostgreSQL vs résolution applicative)
- Forme exacte de la requête d'agrégation consumed (native SQL vs JPQL)
- `p-multiSelect` vs `p-treeSelect` multi pour la liaison catégories
- Soft delete via flag `archived` vs suppression en cascade
- Lookback du rollover (1 mois fixe vs récursif borné)
- Styles Tailwind pour les badges statut (cohérence design system)

## Deferred Ideas

- Enveloppes transversales (cross-account) — backlog v2 confirmé
- Notifications de dépassement (NOTF-01/02, v2)
- Suggestions automatiques de catégorisation (CATG-05/06, v2)
- Seuils configurables par enveloppe (différé)
- Rollover récursif sur plusieurs mois (v1 limite à 1 mois précédent)
- Compteur « hors budget » pour transactions orphelines (v2)
- Export/import d'enveloppes ou d'historique (hors scope v1)
- Visualisation graphique avancée (heatmap, tendances multi-mois)
