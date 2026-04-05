# Phase 3: Accounts & Access Control - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-05
**Phase:** 03-accounts-access-control
**Mode:** discuss
**Areas analyzed:** Enforcement du contrôle d'accès, Attribution de permissions, Archivage, Interface de gestion des comptes

## Gray Areas Presented

### Enforcement du contrôle d'accès
| Question | Options présentées | Choix |
|----------|-------------------|-------|
| Stratégie de filtrage | A (JPQL repository), B (service filtering), C (@PostFilter) | **A — JPQL** |
| GET /{id} sans accès | 404 (inexistant) ou 403 (accès refusé) | **403 Forbidden** |

### Attribution de permissions à la création
| Question | Options présentées | Choix |
|----------|-------------------|-------|
| Compte SHARED : accès pour l'autre user | A (explicite via ACCS-03), B (auto-accès tous les users) | **A — Explicite** |

### Archivage
| Question | Options présentées | Choix |
|----------|-------------------|-------|
| Visibilité dans la liste | A (filtrés par défaut + toggle), B (toujours visibles + badge) | **A — Filtrés par défaut** |
| Désarchivage | Oui ou Non | **Oui** |

### Interface de gestion des comptes
| Question | Options présentées | Choix |
|----------|-------------------|-------|
| Entrée navigation | A (page /accounts sidebar), B (section dashboard) | **A — Page dédiée** (migration vers dashboard Phase 10) |
| Présentation liste | A (p-table PrimeNG), B (cards) | **A — p-table** |
| Création/édition | A (p-dialog), B (page dédiée) | **A — p-dialog** |
| Gestion permissions | A (section dans dialog édition), B (dialog séparé) | **B — Dialog séparé** |

## Corrections Made

Aucune correction — toutes les options recommandées ont été confirmées, sauf :
- 4d : recommandation était A (section dans dialog édition) → utilisateur a choisi **B (dialog séparé)** — plus clair conceptuellement.

## Deferred Ideas

- Widget dashboard comptes → Phase 10
- Invitation utilisateurs → Phase 8
- Connexion Plaid par compte → Phase 7
