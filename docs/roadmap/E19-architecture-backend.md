# E19 — Architecture backend — audit & opportunités de refactoring

> **Durée estimée** : 1-2 jours
> **Statut** : in progress (S19.1–S19.3 créées)
> **Dépend de** : E01–E13 (backend livré)
> **Bloque** : —
> **ADRs activés** : ADR 0005 (graphe directionnel + surface publique)

---

## Objectif

Analyser l'architecture backend livrée (E01–E13) et appliquer les opportunités de deepening identifiées par l'audit du 2026-07-01. Trois frictions concrètes ciblées : un cycle caché dans `budget.service`, cinq modules stubs qui gonflent le graphe directionnel, et une interface `auth.public` incomplète.

Aucune régression fonctionnelle, aucune migration DB, aucun changement de comportement observable : ces stories sont purement structurelles.

---

## Stories

### S19.1 — Extraction de `_budget_queries.py` dans `budget.service`

| Phase | Description | Diff |
|---|---|---|
| **P19.1.1** | Créer `budget/service/_budget_queries.py` (Core handles `_splits`/`_transactions` + `_concerned_budgets`) · Purger les doublons dans `consumption.py` et `threshold_detector.py` · Supprimer l'import lazy + suppression `pyright: ignore[reportPrivateUsage]` | ~60 L |

---

### S19.2 — Suppression des 5 modules stubs du graphe directionnel

| Phase | Description | Diff |
|---|---|---|
| **P19.2.1** | `git rm -r` des 5 répertoires stubs (`forecasting`, `mcp`, `notifications`, `reconciliation`, `savings`) · Mettre à jour `.importlinter` (contrats 1, 2, 2-auth, 2-accounts, 2-budget, 2-transactions, 2-debts, 2-banking, 2-sync) · Vérifier `lint-imports` | ~230 L supprimés |

---

### S19.3 — Re-exporter `require_admin`/`require_member` depuis `auth.public`

| Phase | Description | Diff |
|---|---|---|
| **P19.3.1** | Ajouter les re-exports dans `auth/public.py` · Test de surface (`test_auth_public_surface.py` vérifie que les guards sont importables via le module public) | ~15 L |

---

## Récapitulatif

| Story | Phases | Diff total |
|---|---|---|
| S19.1 | 1 | ~60 L |
| S19.2 | 1 | ~230 L supprimés |
| S19.3 | 1 | ~15 L |

**Total** : 3 stories, 3 phases, ~300 lignes.

## Notes audit

- **Candidat D écarté** : `EDITABLE_AFTER_CONFIRMED` est déjà une `frozenset` en source unique dans `transactions/domain.py`, correctement importée par `lifecycle.py` — pas de duplication réelle.
- **Candidat E écarté** : exposition de `register_subscribers()` depuis les modules — tension avec la justification de centralisation de l'ADR 0005 (lisibilité du câblage global dans `main.py`). ROI insuffisant au stade MVP (8 subscribers seulement).
- Rapport HTML complet archivé dans `/tmp/architecture-review-20260701-200505.html`.
