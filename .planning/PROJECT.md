# Prosperity

## What This Is

Application de gestion de finances personnelles self-hosted pour un foyer. Permet le suivi des comptes bancaires (personnels et communs), la categorisation des transactions, les budgets enveloppes et la synchronisation bancaire automatique via Plaid. Projet open source supportant N utilisateurs avec droits et comptes propres/communs.

## Core Value

Un foyer peut suivre ses finances au quotidien (soldes, transactions, budgets enveloppes) sans effort manuel excessif, grace a la synchronisation bancaire automatique et une interface claire.

## Requirements

### Validated

- [x] Infrastructure dev : Maven + quality gates + JaCoCo coverage enforcement — Validated in Phase 1: Project Foundation
- [x] Frontend scaffolding : Angular 21 + PrimeNG + Tailwind + ESLint + Prettier — Validated in Phase 1: Project Foundation
- [x] Domain model : Money (BigDecimal), entities JPA, enums, BankConnector abstrait — Validated in Phase 1: Project Foundation
- [x] Flyway migrations : schema initial PostgreSQL — Validated in Phase 1: Project Foundation
- [x] Docker Compose + Caddy : stack conteneurisee — Validated in Phase 1: Project Foundation
- [x] CI pipeline : GitHub Actions avec quality gates — Validated in Phase 1: Project Foundation
- [x] Pre-commit hooks : lefthook lint/format — Validated in Phase 1: Project Foundation
- [x] Setup wizard au premier lancement (creation compte admin) — Validated in Phase 2: Authentication Setup Wizard
- [x] Authentification session (Spring Security 7, cookies httpOnly, CSRF SPA mode) — Validated in Phase 2: Authentication Setup Wizard
- [x] Route guards Angular (authGuard, unauthenticatedGuard, setupGuard) — Validated in Phase 2: Authentication Setup Wizard
- [x] Layout shell + dashboard placeholder + routing lazy-loaded — Validated in Phase 2: Authentication Setup Wizard

### Active

- [ ] Authentification BFF cookie flow (JWT cote serveur, cookies httpOnly)
- [ ] Gestion des utilisateurs (invitation, droits, comptes propres/communs)
- [ ] Administration (users, droits, connexions Plaid, monitoring)
- [ ] Creation et gestion de comptes bancaires (personnels + communs)
- [ ] Gestion des acces aux comptes bancaires par utilisateur
- [ ] Import de transactions via Plaid + import initial parametrable
- [ ] Saisie manuelle de transactions + transactions recurrentes (optionnel)
- [ ] Pointage manuel (rapprochement saisie manuelle <-> import Plaid)
- [ ] Categorisation des transactions (categories Plaid comme base, ajustables manuellement)
- [ ] Budgets enveloppes par compte (perso ou commune, parametrable ; rollover parametrable)
- [ ] Gestion de dette interne (objectif remboursement, historique long terme)
- [ ] Dashboard : soldes comptes, suivi enveloppes, graphiques evolution, dernieres transactions
- [ ] Backup PostgreSQL basique (pg_dump planifie)

### Out of Scope

- App native (iOS/Android) -- PWA couvre le besoin mobile
- Multi-devises -- comptes en euros uniquement
- Multi-foyers / mode SaaS -- self-hosted pour un seul foyer
- Real-time chat -- hors perimetre finance
- Categorisation automatique (ML/regles avancees) -- v2, necessite donnees d'entrainement
- Notifications push -- v2, necessite infra push
- Rapports avances -- v2, pas bloquant pour usage quotidien
- Offline first mobile -- v2, sync complexe
- Backup avance (incremental, chiffre, restore automatise) -- v2
- Suggestion auto de pointage -- v2, rapprochement manuel suffit en v1

## Context

- **Foyer** : couple (2 personnes), projet immobilier a venir augmentant les charges mensuelles
- **Situation actuelle** : gestion de tete, aucun outil dedie
- **Motivation** : le projet immobilier rend le suivi mental insuffisant
- **Banques** : Societe Generale + Banque Populaire (confirmees sur Plaid EU/FR)
- **Infra** : serveur Ubuntu 4 cores, 24 Go RAM
- **Stack decidee** : Java 21 + Spring Boot 4.0.x + Angular 21 + PrimeNG 21.x + Tailwind v4 + PostgreSQL 17 + Caddy 2.10.x
- **Architecture** : layered par feature (Controller/Service/Repository) + abstraction strategique (connecteur bancaire), API REST monolithique + SPA separee
- **Connecteur bancaire** : interface abstraite (Plaid interchangeable avec Powens/Salt Edge)
- **ADR-0001** : decisions stack documentees dans `docs/adr/0001-initial-stack.md`
- **ADR-0002** : architecture layered par feature (remplacement hexagonal) dans `docs/adr/0002-architecture-layered.md`

## Constraints

- **Open source** : toutes les dependances MIT ou Apache 2.0
- **Self-hosted** : pas de services cloud payes (hors Plaid)
- **Outillage CI/lint** : versions supportees par Checkstyle, SonarQube, etc. (pas de bleeding edge)
- **Java 21 LTS** : Checkstyle incompatible Java 25
- **Spring Boot 4.0.x** : Boot 3.5 fin OSS juin 2026
- **Connecteur bancaire abstrait** : Plaid interchangeable (interface, pas de couplage direct)
- **Timeline** : pas de deadline, projet personnel "when it's done"
- **Review** : decoupage atomique des phases pour permettre des reviews optimales a chaque etape

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Java 21 au lieu de 25 | Checkstyle incompatible Java 25, SonarQube necessite upgrade | -- Pending |
| Spring Boot 4.0.x au lieu de 3.5 | Boot 3.5 fin OSS juin 2026, migration forcee | -- Pending |
| PrimeNG au lieu d'Angular Material | Meilleur ratio composants finance / integration Tailwind v4 | -- Pending |
| ngx-echarts au lieu de ng2-charts | Candlestick natif, dataZoom, 30+ types de graphiques | -- Pending |
| Caddy au lieu de Nginx/Traefik | Simplicite, HTTPS auto, HTTP/3 | -- Pending |
| PWA au lieu d'app native | Reutilisation code Angular, pas d'app store | -- Pending |
| BFF cookie flow | Securite : JWT cote serveur, cookies httpOnly, Spring Security 7 defaults | -- Pending |
| Enveloppes par compte (pas transversales) | Simplicite v1, une enveloppe = un compte | -- Pending |
| Categorisation Plaid comme base | Reutilise les categories fournies, ajustables manuellement | -- Pending |
| Setup wizard premier lancement | Admin cree via wizard, puis invite les autres | -- Pending |
| Pointage manuel en v1 | Rapprochement saisie/import sans suggestion auto | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check -- still the right priority?
3. Audit Out of Scope -- reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-08 after Phase 5 completion — transactions (CRUD manuel, templates récurrents avec génération, split multi-catégorie, pointage, pagination filtrée, frontend Angular p-table lazy + dialog, 143 tests backend + 100 frontend) complete*
