# Project Research Summary

**Project:** Prosperity — self-hosted personal finance management
**Domain:** Envelope budgeting, multi-comptes, synchro bancaire, foyer multi-utilisateur
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Summary

Prosperity est une application de gestion de finances personnelles self-hosted positionnée sur un créneau précis : le budgeting par enveloppes avec support multi-utilisateurs pour un foyer. Ni Actual Budget ni Firefly III ne gèrent correctement les foyers (comptes partagés, accès par utilisateur, dettes internes). YNAB le fait, mais en mode SaaS payant. L'approche recommandée est un monolithe REST Spring Boot avec SPA Angular, architecture hexagonale allégée, et Plaid pour la synchro bancaire FR/EU. Le stack est mature, toutes les versions sont validées et compatibles.

Le point critique identifié durant la recherche est le remplacement de Liquibase par Flyway : Liquibase 5.0 (oct 2025) a changé de licence vers FSL, incompatible avec la contrainte MIT/Apache 2.0 du projet. Flyway 11.x (Apache 2.0) est le remplacement direct, nativement intégré à Spring Boot 4. Ce changement est greenfield — aucune migration requise — mais l'ADR-0001 doit être mis à jour. L'autre update de version : Caddy 2.11.x (pas 2.10.x, rolling release).

Les risques principaux ne sont pas techniques mais domaine-métier. Le modèle d'enveloppes budgétaires est complexe en edge cases (rollover, remboursements, comptes partagés), le cycle de vie des transactions Plaid (pending → posted) crée des doublons si mal géré, et l'accès aux comptes partagés doit être modélisé au niveau domaine dès le départ — pas seulement au niveau API. Chacun de ces risques a une fenêtre d'intervention précise : domain modeling avant toute persistence, design du sync Plaid avant tout code d'import, modèle d'accès avant les enveloppes.

## Key Findings

### Recommended Stack

Le stack recommandé est entièrement HIGH confidence avec des sources officielles. Le backend repose sur Java 21 LTS + Spring Boot 4.0.5 + Spring Security 7.0.x + Spring Data JPA 4.0.x. **Flyway 11.x remplace Liquibase** (contrainte open source). Le frontend Angular 21 + PrimeNG 21.x + Tailwind v4 + ngx-echarts 21.0.0 est aligné par version avec le cycle Angular. PostgreSQL 17 pour la persistance, Caddy 2.11.x comme reverse proxy, Docker Compose pour le déploiement. MapStruct pour le mapping DTO/entity (élimine le boilerplate du dual-entity model hexagonal). ArchUnit pour valider les règles d'architecture en CI.

**Core technologies:**
- Java 21 LTS + Spring Boot 4.0.5 : backend runtime, support outillage complet (Checkstyle, JaCoCo), OSS jusqu'en nov 2027
- **Flyway 11.x (Apache 2.0)** : migrations DB — remplace Liquibase 5.0 (FSL, non open source)
- Spring Security 7.0.x : BFF cookie auth + CSRF via `CookieCsrfTokenRepository`, intégration Angular native
- Angular 21 + PrimeNG 21.x : SPA/PWA, composants finance riches (p-inputnumber monétaire, p-table avancée)
- Tailwind v4 + tailwindcss-primeui : layout Tailwind + composants PrimeNG, plugin officiel PrimeTek
- ngx-echarts 21.0.0 : graphiques (candlestick, dataZoom, 30+ types), version alignée Angular 21
- Caddy 2.11.x : reverse proxy HTTPS auto, HTTP/3, seule la dernière version est supportée (rolling release)
- Plaid API (plaid-java 39.1.0) : synchro bancaire FR/EU, SG et Banque Populaire confirmées
- MapStruct 1.6.x : mapping compile-time domain ↔ JPA entity, zéro réflexion
- ArchUnit 1.x : tests architecture hexagonale en CI

**À éviter absolument :**
- Liquibase 5.0.x (FSL, pas open source) — utiliser Flyway 11.x
- Lombok (masque le code généré, Java 21 records couvrent les use cases)
- Angular Material (composants finance insuffisants)
- GoCardless/Nordigen (fermé aux nouveaux inscrits depuis juillet 2025)

### Expected Features

Prosperity s'articule autour de 10 features numérotées F1-F10 avec des dépendances explicites. L'authentification (F1) est la fondation de tout. La gestion des comptes (F3) est prérequis pour les enveloppes (F5) et l'import Plaid (F7). Le dashboard (F9) est consommateur de toutes les autres features — à construire en dernier.

**Must have (table stakes — MVP v1) :**
- F1: Authentification — sécurité, multi-utilisateur, BFF cookie flow
- F2: Administration — gestion users, connexions Plaid, santé système
- F3: Gestion des comptes — comptes personnels et partagés
- F4: Contrôle d'accès aux comptes — per-user, per-account permissions
- F5: Enveloppes budgétaires — modèle par-compte, allocation, rollover configurable
- F7: Import Plaid — synchro transactions FR/EU
- F8: Saisie manuelle + pointage — cash, réconciliation
- F9: Dashboard — vue quotidienne, balances, statut enveloppes
- F10: Backup — pg_dump basique

**Should have (différenciateurs) :**
- Household multi-user first-class — aucun concurrent self-hosted ne fait ça
- Suivi dette interne — qui doit combien à qui sur les comptes partagés
- Setup wizard — réduction friction premier démarrage
- Pointage/réconciliation — correspondance saisie manuelle ↔ transaction importée
- Interface BankConnector abstraite — swap Plaid → Powens/Salt Edge sans changer la logique métier

**Defer (v2+) :**
- Transactions récurrentes (templates)
- Rapports avancés (net worth, tendances, year-over-year)
- Push notifications (alertes budget)
- Règles d'auto-catégorisation (après accumulation de données)
- Support multi-devise (hors scope, EUR seulement)

### Architecture Approach

L'architecture hexagonale allégée (Domain / Application / Infrastructure) est la recommandation standard pour ce type d'application. Le domain model reste pur (POJOs, zéro annotation framework), les use cases sont organisés en ports/adapters avec un port par use case (pas de God service). Le dual-entity model sépare les domain entities des JPA entities avec mappers MapStruct. Côté frontend, Angular utilise feature-sliced lazy loading avec smart/dumb component split. Un seul endpoint `DashboardController` agrège les données côté serveur pour éviter les waterfalls HTTP.

**Major components:**
1. Caddy 2.11.x — TLS termination, static files, /api/* proxy
2. Angular SPA/PWA — feature-sliced, lazy-loaded, signals + standalone components
3. Spring Boot REST API — hexagonal, port-per-use-case, controllers fins (3 lignes idéales)
4. Domain Model — POJOs purs, zéro dépendance framework, logique métier encapsulée
5. Persistence Adapters — JPA entities séparées, Spring Data, Flyway migrations
6. Banking Adapter — PlaidBankConnector derrière `BankConnector` port interface
7. PostgreSQL 17 — stockage persistant, index sur `(bank_account_id, transaction_date)` dès le départ

### Critical Pitfalls

1. **Enveloppes modélisées comme CRUD simple** — Prototyper le domain model avec unit tests (allocate, spend, overspend, rollover, refund, partage) avant toute persistence. Phase : domain modeling.

2. **Cycle de vie Plaid pending→posted mal géré** — Utiliser `/transactions/sync` (pas `/get`), appliquer d'abord les removals, stocker le `transaction_id` Plaid comme référence externe (pas PK). Phase : intégration Plaid.

3. **Expiration consentement PSD2 ignorée** — Stocker `consent_expiration_time`, implémenter webhook `PENDING_EXPIRATION`, afficher statut connexion dans l'UI admin. Phase : intégration Plaid.

4. **Race condition CSRF post-login** — Après login, appeler `/api/csrf` pour forcer la génération du token avant toute requête modifiante. Tester end-to-end Angular → API (pas seulement Postman). Phase : auth/sécurité.

5. **Contrôle d'accès comptes partagés au niveau API seulement** — Modéliser `AccountAccess(userId, accountId, role)` comme concept domaine. Filtrer au niveau repository avec `@Query` + contexte utilisateur. Tester avec scénarios 2 utilisateurs dès le début. Phase : gestion des comptes.

6. **Montants monétaires en floating-point** — `BigDecimal` partout en Java, `NUMERIC(15,2)` en PostgreSQL, sérialiser les montants en string JSON. `Money` value object dans le domain. Phase : setup projet / domain model.

7. **Réconciliation sans stratégie de matching** — Modéliser les états de transaction (`MANUAL_UNMATCHED`, `IMPORTED_UNMATCHED`, `MATCHED`) dès le design du modèle. Une paire matched compte une fois dans les balances. Phase : design modèle transaction.

## Implications for Roadmap

Architecture hexagonale impose un ordre de construction naturel : domain → application → infrastructure → frontend. Les dépendances features (F1 → F3 → F5, etc.) renforcent cet ordre.

### Phase 1: Fondations Projet + Domain Model
**Rationale:** Aucune phase ne peut commencer sans le modèle domaine. Les pitfalls critiques (enveloppes trop simples, floating-point money, états de transaction) doivent être résolus avant tout code d'infrastructure. Greenfield = pas de dette à gérer.
**Delivers:** Structure projet, configuration Maven/pnpm/Docker, domain entities pures (Account, Transaction, Envelope, Debt, User), value objects (Money avec BigDecimal), ports in/out définis, tests unitaires domaine (coverage rollover, overspend, refund).
**Addresses:** F3 (modèle account), F5 (modèle envelope), F8 (modèle transaction avec états)
**Avoids:** Pitfall 1 (envelopes CRUD), Pitfall 6 (floating-point money), Pitfall 7 (réconciliation sans matching strategy)
**Research flag:** Patterns domaine bien documentés — skip research-phase. Mais validation du modèle d'enveloppes avec tests unitaires est obligatoire avant de passer à la phase suivante.

### Phase 2: Infrastructure Persistence + Auth
**Rationale:** Le dual-entity model nécessite JPA entities + mappers alignés sur le domain model validé en Phase 1. L'auth BFF cookie est prérequis pour tout endpoint protégé. Flyway migrations SQL définissent le schéma DB.
**Delivers:** JPA entities séparées avec MapStruct mappers, Flyway migrations (schéma complet), Spring Security 7 BFF cookie flow, endpoint `/api/auth/login` + `/api/csrf`, guards Angular, CSRF interceptor.
**Uses:** Flyway 11.x (pas Liquibase), Spring Security 7 CookieCsrfTokenRepository, MapStruct 1.6.x
**Implements:** Persistence adapters, SecurityConfig, CorsConfig
**Avoids:** Pitfall 4 (CSRF race condition) — test end-to-end Angular → login → premier appel API
**Research flag:** Patterns bien documentés (Spring Security BFF, JPA dual-entity) — skip research-phase.

### Phase 3: Gestion Comptes + Contrôle d'Accès
**Rationale:** Fondation pour enveloppes, transactions, et dashboard. Le modèle d'accès (`AccountAccess`) doit exister avant toute feature qui filtre par utilisateur. La household multi-user est le différenciateur — doit être dans les fondations.
**Delivers:** CRUD comptes (personnels + partagés), `AccountAccess(userId, accountId, role)`, API REST accounts, frontend feature `accounts/`, filtrage repository par contexte utilisateur, setup wizard (admin + premier compte).
**Addresses:** F2 (admin), F3 (account management), F4 (access control)
**Avoids:** Pitfall 5 (accès comptes partagés au niveau API seulement) — tests 2 utilisateurs obligatoires
**Research flag:** Patterns bien documentés — skip research-phase.

### Phase 4: Transactions Manuelles + Pointage
**Rationale:** Les transactions sont le cœur opérationnel. Le pointage (réconciliation) doit être conçu dans le modèle transaction dès cette phase — pas ajouté après l'import Plaid. Les enveloppes dépendent des transactions catégorisées.
**Delivers:** Saisie manuelle de transactions (avec catégories Plaid comme base), états de transaction (`MANUAL_UNMATCHED`, etc.), API REST transactions, frontend feature `transactions/`, pointage UI (dialog de réconciliation), pagination curseur.
**Addresses:** F8 (manual entry + pointage)
**Avoids:** Pitfall 7 (réconciliation sans matching strategy), performance trap N+1 et chargement sans pagination
**Research flag:** Patterns bien documentés — skip research-phase.

### Phase 5: Enveloppes Budgétaires
**Rationale:** Les enveloppes dépendent des comptes (Phase 3) et des transactions (Phase 4). La logique domaine est déjà prototypée en Phase 1 — cette phase construit l'infrastructure API + UI dessus.
**Delivers:** CRUD enveloppes par compte, allocation mensuelle, calcul spent/remaining/overspent, rollover configurable (reset ou carry forward), récalcul post-transaction, frontend feature `envelopes/`, indicateurs visuels overspend.
**Addresses:** F5 (envelope budgets)
**Avoids:** Pitfall 1 (envelopes CRUD), performance trap recalcul de toutes les transactions
**Research flag:** Le rollover multi-mois (utilisateur absent 2 mois) et les remboursements sur enveloppe partagée méritent une attention particulière en testing. Skip research-phase mais prévoir des tests d'edge cases explicites.

### Phase 6: Synchro Bancaire Plaid
**Rationale:** Plaid est la feature la plus complexe techniquement avec le plus d'edge cases. Vient après que les comptes, transactions et enveloppes sont stables — l'import alimente des structures déjà validées.
**Delivers:** PlaidBankConnector derrière `BankConnector` port, `/transactions/sync` (pas `/get`), gestion pending→posted, déduplication par `plaid_transaction_id`, stockage `consent_expiration_time`, webhook handlers (`SYNC_UPDATES_AVAILABLE`, `TRANSACTIONS_REMOVED`, `PENDING_EXPIRATION`), connexion initiale (Plaid Link flow), update mode link, UI statut connexion dans admin.
**Addresses:** F7 (Plaid import), F2 (admin — connexions Plaid)
**Avoids:** Pitfall 2 (pending/posted lifecycle), Pitfall 3 (PSD2 consent expiry), intégration gotchas (country_codes FR, webhook signatures, access tokens chiffrés)
**Research flag:** NEEDS research-phase. Plaid EU/FR a des comportements spécifiques (institutions FR, disponibilité produits, quirks pending transactions). Vérifier `/institutions/get_by_id` pour SG et Banque Populaire. Tester en sandbox ET en développement avec vraies credentials.

### Phase 7: Dashboard + Dette Interne
**Rationale:** Le dashboard est consommateur — il ne peut être construit qu'une fois accounts, transactions et envelopes existent avec des données réelles. La dette interne dépend des transactions sur comptes partagés établies en Phase 4.
**Delivers:** `DashboardController` qui agrège (un seul appel API), frontend feature `dashboard/` avec charts ngx-echarts (statut enveloppes, soldes comptes, transactions récentes), feature `debts/` (calcul automatique qui-doit-combien depuis transactions comptes partagés), summary mensuel rollover.
**Addresses:** F9 (dashboard), F6 (internal debt tracking)
**Avoids:** Anti-pattern frontend multi-appels pour une vue (backend agrège), performance trap calcul balances sans cache
**Research flag:** Patterns ECharts + ngx-echarts bien documentés — skip research-phase. Logique dette interne à valider avec scénarios réels.

### Phase 8: Backup + Finalisation Production
**Rationale:** Avant la mise en production, le backup automatique (pg_dump) et la configuration production Caddy (HTTPS, headers sécurité, compression) doivent être en place.
**Delivers:** Script pg_dump automatisé, documentation déploiement self-hosted, Docker Compose production-ready (secrets, volumes persistants, restart policies), Caddy config HTTPS avec headers sécurité, PWA manifeste + service worker.
**Addresses:** F10 (backup)
**Research flag:** Patterns bien documentés — skip research-phase.

### Phase Ordering Rationale

- **Domain avant persistence** : le dual-entity model hexagonal exige que le domain model soit stable avant de créer les JPA entities. Inverser l'ordre force des refactorisations coûteuses.
- **Auth avant tout endpoint protégé** : aucune feature ne peut être testée end-to-end sans auth fonctionnelle.
- **AccountAccess avant Envelopes** : les enveloppes sur comptes partagés nécessitent que les règles d'accès soient déjà en place — sinon chaque feature doit réinventer le filtrage.
- **Transactions avant Envelopes** : les enveloppes calculent leur statut depuis les transactions catégorisées.
- **Plaid après transactions manuelles** : l'import enrichit un modèle déjà stable. Construire Plaid d'abord forcerait à concevoir le modèle transaction avec un prisme Plaid-centrique, rendant le pointage difficile.
- **Dashboard en dernier** : consommateur pur, pas de logique métier propre, dépend de tout le reste.

### Research Flags

Phases nécessitant `/gsd:research-phase` durant la planification :
- **Phase 6 (Synchro Plaid)** : comportements spécifiques Plaid EU/FR, disponibilité produits par institution, gestion webhook en production, chiffrement access tokens. Complexité externe élevée.

Phases avec patterns standard (skip research-phase) :
- **Phase 1** (Domain Model) : DDD patterns, Money value object, ports/adapters — documentation abondante
- **Phase 2** (Persistence + Auth) : Spring Security BFF, JPA dual-entity, Flyway — documentation officielle complète
- **Phase 3** (Comptes + Accès) : CRUD + RBAC patterns — standard
- **Phase 4** (Transactions) : patterns transaction list, pagination curseur — standard
- **Phase 5** (Enveloppes) : logique domaine validée Phase 1, API patterns — standard
- **Phase 7** (Dashboard) : aggregation patterns, ECharts — bien documenté
- **Phase 8** (Production) : Docker Compose, Caddy, PWA — standard

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Toutes les versions vérifiées avec sources officielles (Maven Central, GitHub releases, endoflife.date). Changement Liquibase→Flyway confirmé avec blog officiel Liquibase + licence Flyway GitHub. |
| Features | HIGH | Analyse concurrentielle YNAB + Actual Budget + Firefly III. Feature dependencies explicites et validées par logique domaine. MVP conservateur et justifié. |
| Architecture | HIGH | Patterns hexagonaux vérifiés avec sources Baeldung, Arho Huttunen, Spring Security docs officielles. Build order dérivé des dépendances réelles du code. |
| Pitfalls | HIGH | Pitfalls Plaid vérifiés avec documentation officielle Plaid + blogs techniques Plaid. CSRF issues référencés par numéro de ticket Spring Security. Expérience OSS (Firefly III pain points). |

**Overall confidence:** HIGH

### Gaps to Address

- **springdoc-openapi 2.8.x vs 3.0.x** : version 3.0.0 a un bug connu avec l'API versioning. Utiliser 2.8.x en attendant le fix. À vérifier à nouveau lors de l'implémentation (MEDIUM confidence).
- **Envelope partagée : visibilité par utilisateur** : PITFALLS.md identifie une ambiguïté dans PROJECT.md — "enveloppes par compte, paramétrables". Clarifier : User A et User B voient-ils les mêmes enveloppes sur un compte partagé, ou des vues séparées ? Décision à prendre en Phase 3 avant Phase 5.
- **Plaid Transactions product disponibilité FR** : SG et Banque Populaire sont confirmées au niveau institution, mais la disponibilité du produit `Transactions` spécifiquement n'est pas vérifiée. À valider lors de la Phase 6 avec `/institutions/get_by_id`.
- **Testcontainers 2.x + Spring Boot 4** : MEDIUM confidence (source secondaire). Vérifier la compatibilité `@ServiceConnection` avec la version exacte utilisée lors de l'implémentation.

## Sources

### Primary (HIGH confidence)
- [Spring Boot 4.0 release + endoflife.date](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/) — versions, support timeline
- [Spring Security CSRF docs](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — BFF cookie flow, CookieCsrfTokenRepository
- [Liquibase FSL license announcement](https://www.liquibase.com/blog/liquibase-community-for-the-future-fsl) — changement de licence confirmé
- [Flyway GitHub Apache 2.0](https://github.com/flyway/flyway) — licence open source confirmée
- [Plaid /transactions/sync docs](https://plaid.com/docs/transactions/transactions-data/) — pending/posted lifecycle
- [Plaid EU reauth (180 days)](https://plaid.com/blog/eu-reauth-update/) — PSD2 consent expiry
- [Spring Security issues #12094, #12141, #13424](https://github.com/spring-projects/spring-security/issues/12094) — CSRF race condition
- [PrimeNG releases](https://github.com/primefaces/primeng/releases) — version 21.1.3
- [Caddy releases](https://github.com/caddyserver/caddy/releases) — version 2.11.1
- [plaid-java Maven Central](https://mvnrepository.com/artifact/com.plaid/plaid-java) — version 39.1.0

### Secondary (MEDIUM confidence)
- [Hexagonal Architecture Spring Boot - Arho Huttunen](https://www.arhohuttunen.com/hexagonal-architecture-spring-boot/) — structure packages, patterns
- [Angular 2025 Project Structure - Features Approach](https://www.ismaelramos.dev/blog/angular-2025-project-structure-with-the-features-approach/) — feature-sliced structure
- [BFF Pattern Angular + Spring Boot - Dev Genius](https://blog.devgenius.io/implementing-secure-authentication-with-the-bff-pattern-an-angular-and-spring-boot-guide-8e74cbf667bc) — cookie auth implementation
- [springdoc-openapi GitHub](https://github.com/springdoc/springdoc-openapi) — Spring Boot 4 support, bug v3.0.0
- [Testcontainers 2.0 + Spring Boot 4](https://rieckpil.de/whats-new-for-testing-in-spring-boot-4-0-and-spring-framework-7/) — testing changes
- [YNAB Features](https://www.ynab.com/features) + [Actual Budget](https://actualbudget.org/) + [Firefly III](https://github.com/firefly-iii/firefly-iii) — competitive analysis

---
*Research completed: 2026-03-28*
*Ready for roadmap: yes*
