# Prosperity

## What This Is

Application web auto-hébergée de gestion financière conçue pour un couple. Prosperity centralise comptes personnels et partagés, budgets, transactions prévisionnelles (saisies manuelles, potentiellement récurrentes) et importées (Plaid) avec rapprochement (pointage), et suivi des dettes internes entre conjoints — le tout dans une interface moderne Svelte 5 accessible en PWA. Open source, déployable via Docker sur infrastructure privée.

## Core Value

Le couple dispose d'une vision financière claire, partagée et actualisée — avec un suivi automatique de qui doit combien à qui, éliminant les approximations et les tensions sur l'argent.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

- [ ] Système multi-utilisateurs conjugal (2 rôles : Admin/Standard, comptes personnels et partagés)
- [ ] Authentification sécurisée (JWT + Refresh Tokens, bcrypt 12 rounds)
- [ ] CRUD comptes bancaires avec permissions granulaires (Personnel/Partagé)
- [ ] Modèle transactionnel prévisionnel + rapprochement : saisies manuelles (prévisions, récurrentes) et importées (Plaid), pointage entre les deux, double solde réel/projeté
- [ ] Saisie rapide mobile (quick-add en 3 taps max)
- [ ] Budgets mensuels par catégorie (modes enveloppe et objectif, alertes progressives)
- [ ] Suivi des dettes internes (avances, soldes nets)
- [ ] Dashboard principal (soldes réel + projeté, budgets, dettes, transactions récentes)
- [ ] PWA installable avec cache assets (offline complet en phase ultérieure)
- [ ] Profil et préférences (thème clair/sombre, catégories favorites, devise)
- [ ] Infrastructure Docker (db + api + web) avec déploiement reproductible
- [ ] Pipeline CI/CD progressif (build + tests + lint d'abord, outils avancés ajoutés ensuite — tout exécutable en local)
- [ ] Sécurité OWASP Top 10, headers de sécurité, chiffrement AES-256 tokens Plaid
- [ ] Accessibilité WCAG 2.2 AA
- [ ] Backup PostgreSQL automatisé + monitoring basique (Actuator, logs structurés)

### Out of Scope

- Intégration MCP/IA — Phase 2 post-MVP, objectif d'apprentissage majeur
- Notifications push/email — V2+ (alertes visuelles in-app incluses dans MVP)
- Projections financières complexes — V2+
- Application mobile native — PWA couvre le besoin, Tauri v2 possible si limites PWA
- OAuth/Magic Link — email/password suffit pour 2 utilisateurs
- Redis — cache en mémoire Spring suffit pour 2 utilisateurs
- Plus de 2 utilisateurs — architecture pensée pour 10 max, mais MVP = couple

## Context

**Motivation :** Les solutions existantes (Firefly III, Actual Budget, YNAB, Splitwise) ne combinent pas auto-hébergement, collaboration conjugale native, suivi des dettes internes et technologies modernes dans une interface contemporaine.

**Utilisateurs :**
- Utilisateur principal (admin) : développeur, à l'aise avec interfaces complexes, gère la configuration
- Utilisateur secondaire (standard) : non-technophile, privilégie simplicité et clarté

**Objectifs d'apprentissage :** Ce projet est aussi un terrain d'apprentissage pour Spring Boot moderne (Java 21+), Svelte 5/SvelteKit 2, et préparation à l'intégration MCP/IA post-MVP.

**Documentation existante :** `docs/brief.md`, `docs/prd.md`, `docs/architecture.md` contiennent le brief complet, PRD avec 5 epics détaillées, et l'architecture technique v2 (Vertical Slice + SvelteKit).

## Constraints

- **Stack Backend** : Java 21+ / Spring Boot 3.3+ / PostgreSQL 16 / Liquibase — choix d'apprentissage, non négociable
- **Stack Frontend** : Svelte 5 / SvelteKit 2 / TypeScript / Tailwind CSS — choix d'apprentissage, non négociable
- **Architecture Backend** : Vertical Slice avec Domain Kernel — décidé et documenté dans `docs/architecture.md`
- **Infrastructure** : Docker + Caddy (existant sur serveur) — pas de Redis au MVP
- **Utilisateurs** : 2 (couple), architecture pensée pour 10 max
- **Intégration bancaire** : Plaid Link (banques FR/EU supportées)
- **Performance** : API < 200ms P95, chargement initial < 2s sur 4G
- **Sécurité** : HTTPS obligatoire, conformité OWASP Top 10:2025
- **CI/CD** : Pipeline progressif — build/tests/lint d'abord, SonarQube/SpotBugs/PIT/OWASP ajoutés graduellement. Tout doit être exécutable en local avant push.
- **Monorepo** : Backend et frontend dans le même dépôt

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Svelte 5 + SvelteKit plutôt que React | Bundle réduit, réactivité native, moins de dépendances, objectif d'apprentissage | — Pending |
| Vertical Slice plutôt qu'Hexagonale | Moins de cérémonie, navigation simplifiée pour projet solo, évolutif | — Pending |
| Pas de Redis au MVP | 2 utilisateurs, cache en mémoire Spring suffisant, ajout possible sans changement archi | — Pending |
| Caddy existant plutôt que Nginx en container | Déjà en place sur le serveur, HTTPS automatique, un container de moins | — Pending |
| Pipeline CI progressif | Commencer léger (build/tests/lint), ajouter outils avancés graduellement, tout exécutable en local | — Pending |
| Plaid dans le MVP | Import bancaire automatisé dès la v1, fallback saisie manuelle si erreur | — Pending |
| PWA progressive | Installable + cache assets d'abord, offline/sync dans phase dédiée ultérieure | — Pending |
| Modèle prévisionnel + rapprochement | Saisies = prévisions (récurrentes possibles), importées = réel, pointage entre les deux. Double solde réel/projeté. | — Pending |

---
*Last updated: 2026-03-09 after transaction model revision (prévisionnel + rapprochement)*
