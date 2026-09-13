# E19 — Architecture — audit, refactoring & gardes des invariants

> **Durée estimée** : 1-2 jours
> **Statut** : in progress (S19.1–S19.3 créées ; S19.4 ajoutée le 2026-09-13)
> **Dépend de** : E01–E13 (backend livré)
> **Bloque** : —
> **ADRs activés** : ADR 0005 (graphe directionnel + surface publique) · ADR 0018 (frontière réseau du client) · ADR 0019 (deux portes vers Postgres)

---

## Objectif

Analyser l'architecture backend livrée (E01–E13) et appliquer les opportunités de deepening identifiées par l'audit du 2026-07-01. Trois frictions concrètes ciblées : un cycle caché dans `budget.service`, cinq modules stubs qui gonflent le graphe directionnel, et une interface `auth.public` incomplète.

Aucune régression fonctionnelle, aucune migration DB, aucun changement de comportement observable : ces stories sont purement structurelles.

S19.4 étend l'epic au-delà du backend : elle pose les **gardes mécaniques** des invariants promus par les ADR 0018 (client) et 0019 (backend + migrations), comme `.importlinter` matérialise l'ADR 0005 — un invariant opposable sans filet CI ne tient que par la review.

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

### S19.4 — Gardes mécaniques des ADR 0018 et 0019

Matérialise en CI les invariants **A10–A13** de `docs/architecture.md` (promus le 2026-09-13). Change OpenSpec : `arch-guards-adr-0018-0019`.

| Phase | Description | Diff |
|---|---|---|
| **P19.4.1** | Client — `no-restricted-imports` dans `client/eslint.config.js` (lint bloquant) : zone `ui` (`src/{app,pages,features,components,hooks}/**`, hors tests) ne peut importer `openapi-fetch`, `@powersync/web`, `@microsoft/fetch-event-source` (A10) ; zone `lib` (`src/lib/**`) ne peut importer `@/{app,pages,features,components,hooks}/**` (A11) · test vitest par l'API ESLint (`lintText` + `filePath` virtuel) | ~80 L |
| **P19.4.2** | Backend — `tests/unit/test_architecture_gates.py` : (a) A13, AST des imports `backend.*` d'`alembic/env.py` et `alembic/versions/*.py` bornés à `backend.config`, `backend.shared.models`, `backend.modules.<m>.models` ; (b) A12, scan de `backend/` et `alembic/` : `create_async_engine` / `async_engine_from_config` / `create_engine` admis dans `backend/shared/db.py` et `alembic/env.py` seuls · `docs/ci.md` et `docs/architecture.md` (colonne « Vérifié par ») mis à jour | ~120 L |

> **Écart consigné** : l'ADR 0019 §Conséquences prévoyait `.importlinter` étendu à `alembic` (`root_packages`). Impossible : `alembic/` n'a pas d'`__init__.py` et porte le nom de la bibliothèque `alembic` (`from alembic import context` dans `env.py`) — grimp importerait la lib. La garde est un test AST, même valeur de preuve, sans toucher à `.importlinter`.

---

## Récapitulatif

| Story | Phases | Diff total |
|---|---|---|
| S19.1 | 1 | ~60 L |
| S19.2 | 1 | ~230 L supprimés |
| S19.3 | 1 | ~15 L |
| S19.4 | 2 | ~200 L |

**Total** : 4 stories, 5 phases, ~500 lignes.

## Notes audit

- **Candidat D écarté** : `EDITABLE_AFTER_CONFIRMED` est déjà une `frozenset` en source unique dans `transactions/domain.py`, correctement importée par `lifecycle.py` — pas de duplication réelle.
- **Candidat E écarté** : exposition de `register_subscribers()` depuis les modules — tension avec la justification de centralisation de l'ADR 0005 (lisibilité du câblage global dans `main.py`). ROI insuffisant au stade MVP (8 subscribers seulement).
- Rapport HTML complet archivé dans `/tmp/architecture-review-20260701-200505.html`.
