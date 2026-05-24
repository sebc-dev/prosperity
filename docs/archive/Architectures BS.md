# Architecture — Application Finances Personnelles

> Rapport de synthèse des propositions et recommandation finale **Date** : mai 2026 **Statut** : Recommandation — à valider avant implémentation

---

## 1. Contexte

Application personnelle de gestion de finances, multi-utilisateurs (famille), auto-hébergée, à durée de vie cible de 5 ans, développée en solo avec assistance Claude Code intensive.

**Stack technique de référence** (déjà tranchée dans le doc stack) :

- **Frontend** : Capacitor 8 + React 19 + TypeScript + Vite 6 + Drizzle ORM + Tailwind + shadcn/ui + PowerSync Web/Capacitor SDK
- **Backend** : FastAPI (Python 3.13) + SQLAlchemy 2 async + Alembic + Pydantic v2 + pwdlib (Argon2id)
- **Données** : PostgreSQL 17 + pgcrypto + PowerSync Service (Open Edition)
- **Infrastructure** : Podman/Quadlet + Caddy + Cloudflare Tunnel + Tailscale + Restic→B2

**Contraintes spécifiques** :

- Domaine financier à invariants stricts (double-entrée, devises, intégrité comptable)
- Dépendance externe risquée (Enable Banking, free tier non garanti contractuellement)
- Solo dev → pas de budget pour de l'architecture cargo-cult
- Workflow Claude Code → la structure des fichiers est elle-même un livrable

---

## 2. Périmètre fonctionnel

|#|Feature|Complexité métier|
|---|---|---|
|1|Multi-utilisateur + auth sécurisée|Faible (lib éprouvée)|
|2|Comptes personnels et communs|Moyenne (modèle de propriété)|
|3|Droits et administration|Moyenne (matrice de permissions)|
|4|Import de transactions|Moyenne (Enable Banking + OFX)|
|5|Transactions locales (ponctuelles + récurrentes)|Moyenne (state machine récurrences)|
|6|Pointage transactions locales ↔ bancaires|**Élevée** (algo matching + audit)|
|7|Gestion de budgets|Faible (CRUD enrichi)|
|8|Dettes entre utilisateurs|**Élevée** (invariants zero-sum)|
|9|Transactions non-budgétisées → dettes|**Élevée** (logique métier propre)|
|10|Dashboard multi-soldes (réel, prévisionnel, projeté)|**Élevée** (logique de projection)|
|11|Épargne avec objectifs et prévision|Moyenne (projection simple)|
|12|Notifications (email, push, in-app)|Faible (abstraction canal)|

**Constat** : 4 features en "complexité élevée" justifient un investissement architectural ciblé. Les 8 autres sont des CRUD enrichis qui ne le justifient pas.

---

## 3. Options d'architecture backend

### Option A — Layered classique (style Spring MVC)

```
api/routes → services → repositories → models (SQLAlchemy)
schemas/   (Pydantic API)
```

**Pour**

- Familier (mapping direct avec Controller → Service → Repository)
- Démarrage rapide, peu de boilerplate
- FastAPI + SQLAlchemy 2 async marchent nativement ainsi
- Claude Code génère ce pattern par défaut

**Contre**

- Le service tend à devenir un god object (cf. `RequeteurService` Préliq)
- Logique métier couplée à SQLAlchemy → tests = besoin d'une vraie DB ou mocks pénibles
- Abstraction `BankingProvider` devient une rustine plutôt qu'un design
- Invariants financiers (double-entrée, Money, dettes zero-sum) difficiles à garantir

### Option B — Hexagonal complet (Ports & Adapters)

```
domain/         Pydantic v2 pur (Money, Account, Transaction, Split)
  ports.py      AccountRepository, BankingProvider, Clock (ABC)
application/    use cases (commands / queries)
adapters/
  inbound/http/    routes FastAPI, schemas API
  outbound/        persistence SQLAlchemy, banking providers
config/         pydantic-settings
```

**Pour**

- Domaine financier testable en `pytest` sans Postgres / HTTP / Enable Banking
- Cohérent avec la philosophie Pydantic 3-couches (DB / API / Domain)
- Port `BankingProvider` = porte de sortie naturelle si free tier Enable Banking saute
- Excellente spécification exécutable pour Claude Code

**Contre**

- Plus de fichiers, plus de mapping (DTO ↔ domain ↔ ORM)
- Sur-abstraction sur les CRUD simples (Budget, SavingsGoal)
- Discipline élevée requise pour ne pas laisser le domaine fuir dans `application/`

### Option C — Vertical Slice / Modular Monolith

```
modules/
  auth/         routes + service + model + tests (self-contained)
  accounts/
  transactions/
  banking/      (Enable Banking + OFX)
  budget/
  savings/
shared/         Money, Currency, base classes
api/            assemblage des routers, middleware
```

Chaque module est un bounded context. Hétérogénéité acceptée : hexagonal là où c'est utile, layered là où ça suffit.

**Pour**

- Organisation par feature business, pas par couche technique
- Excellent pour Claude Code : un module = un contexte tenable
- Extraction microservice possible plus tard
- Permet de moduler l'investissement architectural par module
- Évite le piège du dossier `services/` qui finit en fourre-tout à 50 fichiers

**Contre**

- Discipline requise contre les dépendances croisées entre modules
- Partage de modèles transverses (User, Money) demande une convention claire
- Alembic gère mal les modèles éclatés (config explicite nécessaire)

---

## 4. Options d'architecture frontend

### Option A — Feature-based plat

```
src/
  features/
    accounts/, transactions/, budget/
  shared/    ui (shadcn), lib, hooks
  app/       router, providers, layouts
```

**Pour**

- Suffisant pour un projet solo
- Peu de cérémonie, lisible immédiatement
- Aligné avec l'usage naturel de shadcn/ui

**Contre**

- Pas de règle formelle sur la définition de "feature" → dérive possible
- Pas de notion d'entité partagée entre features

### Option B — Feature-Sliced Design (FSD)

```
app/ → pages/ → widgets/ → features/ → entities/ → shared/
```

Méthodologie formelle, règle stricte d'import descendant uniquement.

**Pour**

- Convention claire et auto-portante
- Claude Code la respecte bien quand documentée dans `CLAUDE.md`
- `entities/transaction` partage type + hooks + composants entre features
- Bonne fit avec Drizzle + TanStack Query

**Contre**

- Vocabulaire qui demande adaptation (slice, segment, layer)
- Peut paraître bureaucratique pour ~15 écrans
- Communauté francophone limitée

### Option C — DDD frontend (mirror du backend hexagonal)

```
src/
  domain/, application/, infrastructure/, ui/
```

**Pour**

- Symétrie parfaite avec backend hexagonal
- Logique offline testable sans navigateur
- `Money` TS = mirror du `Money` Pydantic

**Contre**

- Inhabituel en TS/React, peu de patterns établis
- Over-engineering pour des écrans majoritairement CRUD
- Drizzle + PowerSync ont déjà leurs abstractions

---

## 5. Revue critique : sur ou sous-engineering ?

### Ce qui était excessif dans la proposition initiale

- **Hexagonal complet sur le module transactions** : un domaine Pydantic pur + ports en ABC, c'était trop. Un `Protocol` Python (typage structurel) sur les points d'extension réels suffit.
- **`application/` séparé avec commands/queries** : du CQRS-light déguisé, sans valeur à cette échelle.
- **Symétrie hexagonale stricte côté front** : un `components/business/` joue le même rôle qu'`entities/` sans le vocabulaire FSD.

### Ce qui reste justifié, même solo

- **Modular monolith** : 12 features sur 7 contextes → un layered plat devient ingérable en 6 mois. C'est du rangement, pas de l'architecture.
- **Value object `Money`** : 30 lignes qui éliminent une classe entière de bugs financiers. Non négociable.
- **Abstraction `BankingProvider`** (Protocol + 1 impl + Mock) : coûte zéro ligne supplémentaire et te donne une porte de sortie.
- **Modèle de domaine pour les dettes** : tu vas le faire de toute façon. Le faire proprement maintenant coûte autant que le faire mal et le réécrire dans 8 mois.

### Le vrai critère

Le coût de l'architecture vit dans les **mappings entre couches** (DTO ↔ domain ↔ ORM). Tu paies cher quand tu en mets partout, tu paies juste là où c'est utile.

→ Mettre l'effort où il y a des invariants à protéger. Ne pas le mettre ailleurs.

---

## 6. Recommandation finale

### Backend : Modular Monolith avec domaine ciblé

```
backend/
  modules/
    auth/                 routes, service, models, schemas
    accounts/             + droits (personnel / commun, RBAC simple)
    transactions/         + domain.py (Money, Transaction, Split, règles)
    reconciliation/       + domain.py (matching local ↔ bancaire, audit trail)
    banking/              + provider.py (Protocol + EnableBanking + OFX)
    budget/               CRUD enrichi
    debts/                + domain.py (calcul, invariants zero-sum)
    forecasting/          + service.py (projection soldes, récurrences)
    savings/              CRUD + projection simple
    notifications/        + channels.py (Protocol Email/Push/InApp)
  shared/
    money.py              Value object Pydantic v2
    currency.py
    permissions.py        décorateurs FastAPI
  config.py               pydantic-settings
  alembic/
  tests/
```

**Règle de modulation** :

|Module|A un `domain.py` ?|Justification|
|---|---|---|
|transactions|Oui|Double-entrée, Money, splits|
|reconciliation|Oui|Algo matching + audit|
|debts|Oui|Invariants zero-sum entre users|
|forecasting|Service riche|Projection multi-soldes|
|banking|Protocol + impls|Porte de sortie Enable Banking|
|notifications|Protocol canaux|Email/Push/InApp interchangeables|
|auth, accounts, budget, savings|Non|CRUD enrichis, layered suffit|

**Pas de** : `application/` séparé, mappers systématiques DTO↔domain↔ORM, ABC formelles partout, CQRS, event sourcing.

**Convention Pydantic 3 usages** :

- `schemas.py` → contrat API (input/output)
- `domain.py` → modèles métier purs (Money, value objects, règles)
- `config.py` → pydantic-settings (env vars validées au démarrage)

### Frontend : Feature-based + composants business

```
client/
  src/
    app/                  router, providers, layout, theme
    pages/                un fichier = une route
    features/             interactions complètes (add-transaction, reconcile-bank,
                          settle-debt, link-bank-account…)
    components/
      business/           TransactionRow, AccountCard, DebtSummary, BalancePanel
      ui/                 shadcn (généré)
    lib/
      powersync/          setup, schema, write upload handler
      drizzle/            schema local
      api/                client typé OpenAPI
      money.ts            mirror du Money Pydantic
    hooks/                partagés (useUser, usePermissions…)
    types/                générés depuis OpenAPI
  capacitor.config.ts
  vite.config.ts
```

**Pas de** : FSD formelle complète, couche `entities/`, séparation `domain/application/infrastructure/ui`.

### Tests

|Cible|Outil|Approche|
|---|---|---|
|`modules/*/domain.py`|pytest pur|Tests unitaires sans DB, rapides|
|`modules/*/service.py`|pytest + factories|Tests avec DB testcontainers|
|`modules/banking/provider.py`|pytest + fixtures JSON|Tests de contrat offline|
|Endpoints HTTP|pytest + httpx.AsyncClient|Tests d'intégration|
|`components/business/`|Vitest + Testing Library|Tests composants isolés|
|`features/`|Vitest + Testing Library|Tests d'interaction|
|Parcours critiques|Playwright|Saisie offline → sync online, multi-device|

**Cible** : couverture domaine ≥ 90%, couverture services ≥ 70%, parcours E2E sur les 5 flux critiques (login, ajout transaction, pointage, calcul dette, lien bancaire).

---

## 7. Principe directeur

> **L'architecture suffisante** : ni layered naïf qui finit en god service à 18 mois, ni hexagonal cargo-cult qui coûte trois fois plus à écrire pour les CRUD.
> 
> Le coût se paie dans les mappings entre couches. On en met là où il y a des invariants à protéger. On n'en met pas ailleurs.

**Test de validation à 12 mois** : si une nouvelle feature complexe arrive (ex. "split d'une transaction commune avec règle de répartition dynamique par catégorie"), on doit savoir immédiatement dans quel(s) module(s) elle vit. Si oui → l'architecture tient. Si non → signal d'alerte.

---

## 8. Prochaines étapes

1. **Valider le périmètre des modules** : confirmer la liste, identifier les chevauchements (ex. forecasting ↔ savings, debts ↔ accounts communs).
2. **Détailler le module `transactions`** : value object `Money`, modèle `Transaction` avec splits, invariants, tests d'exemple.
3. **Détailler le module `debts`** : modèle de propagation depuis les transactions non-budgétisées, invariants zero-sum, exemples concrets multi-users.
4. **Spécifier le contrat `BankingProvider`** : signatures Protocol, modèles de retour, gestion d'erreurs typées, mock pour tests.
5. **Définir le schéma Drizzle client** : tables locales, index pour les listes, contraintes de sync PowerSync.
6. **Documenter dans `CLAUDE.md`** : conventions de code, structure des modules, règles d'import, commandes principales.
7. **Créer le skill `finance-domain-model`** : référence injectable pour Claude Code sur les invariants du domaine.

---

## Annexe — Comparaison synthétique

|Critère|Layered (A)|Hexagonal (B)|Modular Monolith (C)|**Recommandé**|
|---|---|---|---|---|
|Time-to-MVP|⭐⭐⭐|⭐|⭐⭐|⭐⭐|
|Testabilité domaine|⭐|⭐⭐⭐|⭐⭐ (selon module)|⭐⭐|
|Protection des invariants|⭐|⭐⭐⭐|⭐⭐⭐ (sur modules ciblés)|⭐⭐⭐|
|Évolutivité 5 ans|⭐|⭐⭐⭐|⭐⭐⭐|⭐⭐⭐|
|Lisibilité solo|⭐⭐⭐|⭐|⭐⭐⭐|⭐⭐⭐|
|Coût initial|⭐⭐⭐|⭐|⭐⭐|⭐⭐|
|Compatibilité Claude Code|⭐⭐|⭐⭐|⭐⭐⭐|⭐⭐⭐|
|Sortie de dépendance externe|⭐|⭐⭐⭐|⭐⭐⭐|⭐⭐⭐|

(⭐ = faible, ⭐⭐⭐ = élevé)