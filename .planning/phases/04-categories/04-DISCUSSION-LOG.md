# Phase 4: Categories - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-05
**Phase:** 04-categories
**Mode:** discuss
**Areas discussed:** Propriété des catégories, Seeding Plaid, Portée de CATG-02, UI gestion catégories

## Gray Areas Presented

| Zone grise | Options présentées | Choix retenu |
|---|---|---|
| Propriété des catégories | Globales foyer / Par utilisateur | Globales foyer |
| Seeding Plaid | Flyway SQL curated / ApplicationRunner / Taxonomie complète ~80 | Flyway SQL curated (~20-30 catégories FR) |
| Portée de CATG-02 | Phase 4 endpoint seul / Phase 5 complètement | Phase 4 — endpoint PATCH seul |
| UI gestion catégories | Page dédiée /categories / Inline uniquement / Page + inline | Page dédiée /categories |

## Corrections Made

Aucune correction — toutes les options recommandées retenues.

## Codebase Context Used

- `Category.java` — entité existante (Phase 1), correcte structurellement, requiert `is_system`
- `CategoryRepository.java` — vide, à enrichir
- `V004__create_categories.sql` — table déjà créée, migration complémentaire requise
- `Transaction.java` — champ `category` FK déjà présent, endpoint PATCH à implémenter
- `frontend/src/app/accounts/` — modèle de structure Angular à répliquer
