# Phase 5: Transactions - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-06
**Phase:** 05-transactions
**Mode:** assumptions
**Areas analyzed:** Transaction Data Model, Split Transactions, Recurring Templates, Access Control, Pagination & Filtres, Frontend Pattern, Pointage/Réconciliation

## Assumptions Presented

### Transaction CRUD & Data Model
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Entité `Transaction` complète pour CRUD de base (TXNS-01/02/03) | Confident | `transaction/Transaction.java` — champs existants validés |
| Split nécessite nouvelle table `transaction_splits` | Confident | `V005__create_transactions.sql` — single `category_id` FK, aucun `TransactionSplit` dans le codebase |

### Recurring Templates
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Nouvelle entité `RecurringTemplate` + migration V012 requise | Likely | `shared/TransactionSource.java` a `RECURRING` mais zéro fichier `Recurring*` dans le projet |

### Access Control
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Accès transactions hérité du compte lié (`AccountAccess`) | Confident | `TransactionService.java` — `findById()` sans vérification d'accès, gap visible |
| Pattern à appliquer : `AccountAccessRepository` + 403 vs 404 distinction | Confident | `AccountService.java` — pattern établi en Phase 3 |

### Pagination & Filtres
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Spring Data `Pageable` + JPQL, retourne `Page<Transaction>` | Likely | Zéro hit `Pageable` dans le backend actuel — premier usage |
| Endpoint scopé par compte : `GET /api/accounts/{id}/transactions` | Likely | Liste cross-comptes = Dashboard Phase 10 |

### Frontend Pattern
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Structure identique modules accounts/categories | Confident | `categories/` module = réplique exacte du pattern Phase 3 |
| `CategorySelector` réutilisable sans modification | Confident | Phase 4 CONTEXT D-10 — créé explicitement pour Phase 5 |

### Pointage / Réconciliation
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| `pointed: boolean` suffisant pour TXNS-05 | Confident | `Transaction.java` ligne 65 — champ dédié séparé de `TransactionState` |
| `TransactionState.MATCHED` pour lien Phase 7 (Plaid) | Confident | Enum à 3 valeurs — MANUAL_UNMATCHED initial pour Phase 5 |

## Corrections Made

No corrections — all assumptions confirmed by user.

## External Research

No external research needed — codebase provided sufficient evidence for all assumptions.
