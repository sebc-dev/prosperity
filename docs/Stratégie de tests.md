# Stratégie de tests — Application Finances Personnelles

> Version post-grilling consolidée
> **Date** : 2026-05-24
> **Statut** : Décisions tranchées, prêt pour implémentation
> **Docs liés** : [`CONTEXT.md`](../CONTEXT.md) (glossaire), [`docs/adr/`](./adr/) (14 ADRs), [`Architectures BS.md`](./Architectures%20BS.md), [`Sans titre.md`](./Sans%20titre.md)
> **Archive** : [`archive/Stratégie de tests.md`](./archive/Strat%C3%A9gie%20de%20tests.md) (version exploratoire pré-grilling, mai 2026)

---

## 1. Contexte

Application personnelle multi-utilisateurs (famille), auto-hébergée, durée de vie cible 5 ans, développée en solo avec assistance Claude Code intensive.

**Contraintes spécifiques pesant sur la stratégie de test** :

- Domaine financier à invariants stricts (double-entrée, devises, dettes zero-sum, reconciliation)
- Architecture offline-first avec synchronisation PowerSync server-authoritative
- Dépendance externe risquée (Enable Banking, free tier non garanti contractuellement)
- Solo dev → budget de temps de test fini, prioriser ce qui rapporte
- Workflow Claude Code → la suite de tests est le filet de sécurité principal face au refactoring assisté
- Stack Capacitor : un seul codebase TS/React pour PWA Web et Android, donc une seule suite Vitest + Playwright

---

## 2. Principes directeurs

1. **L'effort de test va là où il y a des invariants à protéger.** Les modules à `domain.py` riche (`transactions`, `reconciliation`, `debts`, `forecasting`, `mcp`) sont sur-investis. Les CRUD enrichis (`budget`, `savings`, `auth`, `accounts`) sont testés sobrement.

2. **Les tests sont le filet face à Claude Code.** Un assistant qui génère beaucoup de code rapidement amplifie la surface d'erreur silencieuse. La suite doit pouvoir affirmer "ce refactor n'a rien cassé" sans relire 800 lignes. Effort orienté invariants + tests d'architecture, pas couverture cosmétique.

3. **TDD strict sur le domaine, libre ailleurs.** Sur les modules à `domain.py`, on écrit le test d'abord. Non négociable parce que les invariants sont mieux pensés en les exprimant comme tests avant d'avoir un biais d'implémentation.

4. **Pyramide enrichie d'intégration DB substantielle.** Pyramide classique (beaucoup d'unitaires, peu d'E2E) élargie à la base avec une couche d'intégration DB (testcontainers Postgres) substantielle. Le testing trophy pur ne convient pas parce que le domaine financier mérite vraiment ses tests unitaires de domaine.

5. **Property-based pour les invariants, example-based pour les cas concrets.** Hypothesis sur les value objects et les fonctions pures du domaine. pytest example-based pour les régressions, les scénarios métier précis, et tout ce qui a des effets de bord.

6. **Tests d'architecture comme garde-fou structurel.** L'architecture Modular Monolith ne tient que si la discipline d'import est mécaniquement vérifiée. Probablement le test à plus haut ROI face à Claude Code (cf. ADR 0005).

7. **Ce qui n'est pas testé est documenté.** Fichiers générés (clients OpenAPI, types TS), bibliothèques tierces (PowerSync SDK, shadcn/ui non modifiés), schémas Pydantic d'API (couverts par le typage), CSS pur — pas testés. Choix, pas oubli.

---

## 3. Architecture des tests

```
                          Playwright (5 parcours)
                          ────────────────────────
                       Tests d'intégration HTTP (httpx)
                       Tests de contract Enable Banking
                       Tests de migration Alembic
                       Tests write upload handler (sync)
                    ──────────────────────────────────
                  Tests d'intégration DB (testcontainers)
                  Tests Vitest + Testing Library (features)
               ────────────────────────────────────────────
              Tests unitaires de domaine (pytest + Hypothesis)
              Tests unitaires de composants (Vitest)
              Tests d'architecture (import-linter)
            ──────────────────────────────────────────────────
```

Lecture : la base (unitaires + archi) est la plus large, la plus rapide, exécutée à chaque commit. Les couches supérieures sont plus chères, plus lentes, plus rares.

---

## 4. Backend — stratégie par couche

### 4.1 Tests unitaires de domaine

**Cible** : `modules/*/domain.py` (modules `transactions`, `reconciliation`, `debts`, `forecasting`, `mcp`, `banking` light) et `shared/money.py`, `shared/currency.py`, `shared/events.py`.

**Outils** : pytest, Hypothesis, pas de DB, pas de réseau, pas de FastAPI.

**Approche** : TDD strict. Pour chaque règle métier identifiée dans CONTEXT.md ou un ADR, un ou plusieurs tests example-based plus une ou plusieurs propriétés Hypothesis quand l'invariant est quantifiable.

**Invariants ciblés (extraits, voir ADRs pour la liste complète)** :

- `Money + Money` n'autorise pas le mélange de devises (lève `IncompatibleCurrencyError`).
- Somme des `splits` d'une `Transaction` `confirmed` = 0 pour toute combinaison (ADR 0001).
- Aucun champ gelé d'une transaction `confirmed` n'est éditable hors du set explicite (ADR 0001).
- Matrice de dettes antisymétrique : `debt(A→B) == -debt(B→A)`.
- `DebtCalculator` idempotent : appliquer deux fois sur la même transaction donne le même set de dettes (ADR 0002).
- Conservation du solde net entre deux contreparties : `sum(debts entre A et B) - sum(settlement_lines entre A et B) == 0` après apurement complet (ADR 0011).
- `MatchScorer` déterministe : mêmes inputs → même score ; ajouter une transaction étrangère ne change pas les autres scores.
- Cycle prevention catégories : toute mutation `parent_id` qui passe la validation ne crée pas de cycle.
- Reconciliation : confirmer une `Reconciliation` marque les autres `suggested` partageant le même `bank_transaction_id` comme `rejected`.
- `Settlement` non-virtuel : `sum(SettlementLine.amount) == linked_transaction.amount` ; tous les `debt_id` concernent les deux mêmes contreparties.

**Convention de nommage** : `tests/unit/domain/test_<module>.py`, classe `Test<Concept>`, méthodes `test_<comportement>` (example) ou `test_property_<invariant>` (Hypothesis).

### 4.2 Property-based testing (Hypothesis)

**Périmètre** : strictement limité au domaine pur. Pas d'Hypothesis sur les services (effets de bord), les endpoints (HTTP), ou la logique frontend.

**Investissement initial** : une `tests/strategies.py` partagée avec les stratégies réutilisables. Estimation : ~200 lignes, ~1-1.5 jour.

```python
# tests/strategies.py — extrait illustratif
from hypothesis import strategies as st

@st.composite
def money_strategy(draw, currency=None):
    currency = currency or draw(st.sampled_from(["EUR", "USD", "GBP"]))
    amount = draw(st.integers(min_value=-10**9, max_value=10**9))
    return Money(amount_cents=amount, currency=currency)

@st.composite
def balanced_splits_strategy(draw, n_splits=None):
    n = n_splits or draw(st.integers(min_value=2, max_value=5))
    # génère n-1 splits aléatoires, le dernier compense pour zero-sum
    ...

@st.composite
def settlement_strategy(draw, debts: list[Debt]):
    # génère un Settlement valide qui apure un sous-ensemble des debts donnés
    ...
```

**Configuration** : `max_examples=50` en push CI, `max_examples=500` en nightly. Deadlines élevées (1s par exemple) pour ne pas avoir de faux flaky.

**Cohabitation property + example** : utiliser `@example()` pour épingler les cas concrets connus en plus de la génération aléatoire.

### 4.3 Tests d'architecture (import-linter)

**Matérialise** l'ADR 0005 (graphe directionnel + public surface).

**Contrats à écrire dans `.importlinter`** :

```toml
[importlinter]
root_package = "backend"

# Contrat 1 — Graphe directionnel par layers
[[importlinter.contracts]]
name = "Directional graph respected"
type = "layers"
layers = [
    "backend.modules.mcp",
    "backend.modules.sync",
    "backend.modules.reconciliation | backend.modules.forecasting | backend.modules.debts | backend.modules.notifications",
    "backend.modules.banking | backend.modules.transactions | backend.modules.budget",
    "backend.modules.accounts",
    "backend.modules.auth",
    "backend.shared",
]

# Contrat 2 — Pas d'import des internals cross-module
[[importlinter.contracts]]
name = "Only public surface importable cross-module"
type = "forbidden"
source_modules = ["backend.modules.*"]
forbidden_modules = [
    "backend.modules.*.service",
    "backend.modules.*.models",
    "backend.modules.*.domain",
    "backend.modules.*.repository",
    "backend.modules.*.transports",
    "backend.modules.*.handlers",
]
# Note : un module peut accéder à ses propres internals. Importer son propre
# public.py depuis ses internals n'est pas interdit non plus.

# Contrat 3 — shared isolé
[[importlinter.contracts]]
name = "shared imports nothing of modules"
type = "forbidden"
source_modules = ["backend.shared"]
forbidden_modules = ["backend.modules.*"]

# Contrat 4 — Seul banking.service.polling peut importer BankingProvider
[[importlinter.contracts]]
name = "BankingProvider used only by polling"
type = "forbidden"
source_modules = ["backend"]
forbidden_modules = ["backend.modules.banking.providers"]
ignore_imports = [
    "backend.modules.banking.service.polling -> backend.modules.banking.providers",
    "backend.modules.banking.public -> backend.modules.banking.providers",
]

# Contrat 5 — MCP n'est jamais importé par un autre module
[[importlinter.contracts]]
name = "MCP module is consumer-only"
type = "forbidden"
source_modules = [
    "backend.modules.auth", "backend.modules.accounts", "backend.modules.transactions",
    "backend.modules.budget", "backend.modules.banking", "backend.modules.reconciliation",
    "backend.modules.forecasting", "backend.modules.debts", "backend.modules.notifications",
    "backend.modules.savings", "backend.modules.sync",
]
forbidden_modules = ["backend.modules.mcp"]
```

**Coût** : ~80 lignes de config + 0 ligne de code de test (import-linter s'exécute via CLI). Coût négligeable par rapport au ROI face à Claude Code.

**Anti-pattern à proscrire absolument** : `# noqa: contract-N` qui s'accumulent. Une violation = soit la règle est mal calibrée (corriger la règle), soit l'architecture dérive (corriger le code).

### 4.4 Tests d'intégration avec DB

**Cible** : `modules/*/service.py`, repositories, logique transactionnelle, en particulier la matérialisation synchrone des dettes par `debts.service` après chaque write de transaction (cf. ADR 0002).

**Outils** : pytest, testcontainers-python (Postgres 17), SQLAlchemy 2 async, factory-boy pour la donnée.

**Stratégie** : une fixture pytest `db_session` qui démarre un container Postgres par session de test, applique les migrations Alembic complètes, et fournit une session async avec rollback automatique entre tests.

**Convention de nommage** : `tests/integration/<module>/test_<service>.py`.

**Performance** : ~10-30 secondes de démarrage pour le container, négligeable sur une session. Mitigations : `pytest --reuse-db` en local, container partagé en CI.

### 4.5 Tests d'intégration HTTP et write upload handler

**Cible** : routes FastAPI, sérialisation, auth, RBAC, **write upload handler PowerSync** (cf. ADR 0014).

**Outils** : pytest, `httpx.AsyncClient` avec `ASGITransport` (pas de port réseau), réutilisation de la fixture `db_session`.

**Approche** : un test d'endpoint vérifie le contrat HTTP (status code, schema de réponse, auth requise). Il ne re-teste pas la logique métier déjà couverte au niveau service.

**Cas particulier — write upload handler (couverture exhaustive)** : le contrat à 10 étapes de l'ADR 0014 doit être couvert exhaustivement :

- Idempotence : rejouer la même mutation N fois (même `client_request_id` UUID v7) → même état final, un seul commit.
- Ordering : batch de N mutations dans l'ordre client, dépendances résolues (création compte puis transaction sur ce compte dans le même batch).
- Erreur récupérable (`validation_error`, `immutable_field_violation`) : `WriteResult.error` correctement typé, mutation purgée côté client.
- Erreur serveur (500) : pas de commit partiel, PowerSync retry attendu.
- Matérialisation synchrone des dettes après write d'une transaction : tests qui vérifient l'état de la table `debts` après commit.
- Isolation cross-user : mutation d'Alice ne peut jamais affecter le compte de Bob (auth check).

**Property Hypothesis** : pour toute permutation valide d'un batch de mutations, l'état final converge selon l'ordering préservé.

### 4.6 Tests de migrations Alembic

Sujet souvent sous-investi, particulièrement risqué pour un domaine financier où une migration ratée = corruption silencieuse.

**Trois niveaux** :

| Niveau | Cible | Quand |
|---|---|---|
| 1 — Schema check | Toutes les migrations | Push CI |
| 2 — Round-trip + data | Migrations à backfill | Nightly CI |
| 3 — Sur dump prod | Migrations à risque | Manuel, avant release |

**Niveau 1** : test pytest qui prend une DB vide via testcontainers, applique `alembic upgrade head`, et compare le schéma résultant à un schéma de référence (snapshot SQL versionné). Détecte les erreurs syntaxiques et les oublis.

**Niveau 2** : pour chaque migration nommée selon la convention `*_backfill.py`, un test pytest dédié qui restaure une fixture représentative à l'état pré-migration, applique `upgrade`, vérifie l'état des données via queries d'assertion, et si `downgrade` est défini, vérifie que `down → up` converge.

**Niveau 3** : non automatisé, documenté dans `runbooks/release.md`. Procédure : restaurer le dernier backup Restic en local, appliquer la migration, valider manuellement. ~30 min/release, ~5 fois par an.

### 4.7 Tests de contract Enable Banking

Trois niveaux distincts (matérialisent l'ADR 0009 séparation Provider/Reader) :

**Niveau A — Tests unitaires de l'adaptateur** : mock du client HTTP, vérification que `EnableBankingProvider` produit les bons appels et parse correctement les réponses, **et lève les bonnes exceptions typées** (`ConsentExpiredError`, `RateLimitedError`, etc.). Push CI.

**Niveau B — Tests de contract sur fixtures JSON** : fixtures versionnées dans `tests/fixtures/enable_banking/`, validation par les modèles Pydantic générés depuis l'OpenAPI Enable Banking via `datamodel-code-generator`. Si Enable change un champ obligatoire, les fixtures cessent de valider → CI rouge. Push CI.

**Niveau C — Appels réels à l'API Enable Banking** : nightly CI uniquement, sur un compte sandbox/test dédié (jamais le compte personnel), avec tolérance d'échec (3 échecs consécutifs pour alerter). Détecte les breaking changes invisibles côté fixtures et la deprecation de routes.

**Script de refresh des fixtures** : `scripts/refresh_enable_banking_fixtures.py` exécuté manuellement après chaque release Enable annoncée ou trimestriellement. Le diff git sur les fixtures est le meilleur révélateur de changement de contrat.

**Contrainte SCA 180 jours** : la session du compte CI expirera tous les 180 jours, nécessite intervention manuelle. Procédure documentée dans `runbooks/enable_banking.md`.

### 4.8 Tests du module `mcp`

Module à `domain.py` (PendingAction immutable, audit lineage, heuristiques compromission) — TDD strict.

**Property Hypothesis** :
- Audit lineage immutable : `proposed_payload` jamais réécrit en place ; `modify_then_confirm` crée une nouvelle entité avec FK `derived_from_action_id`.
- Heuristiques Tier 1 : pour toute séquence de requêtes simulées, la désactivation auto se déclenche **uniquement** sur les signaux binaires (`scope_violation ≥ 3 en 5 min`).
- Rate limiting par PAT : pour tout débit > 60/min, requêtes 61+ → HTTP 429.

**Tests d'intégration tools MCP** : chaque tool V1 (`list_accounts`, `analyze_spending`, etc.) testé contre une DB peuplée, vérifie les filtres user_id (un PAT d'Alice ne voit jamais les données de Bob).

---

## 5. Frontend — stratégie par couche

### 5.1 Tests unitaires de composants

**Cible** : `components/business/` (TransactionRow, AccountCard, DebtSummary, BalancePanel, PendingActionCard, SavingsGoalCard).

**Outils** : Vitest, @testing-library/react, @testing-library/user-event.

**Approche** : tests d'interaction depuis le point de vue utilisateur (cliquer, taper, observer), pas d'introspection d'état interne React. Mocking minimal des hooks (`useUser`, `usePermissions`) via une fixture de provider.

**Hors périmètre** : composants shadcn/ui non modifiés (déjà testés en amont), composants purement présentationnels sans logique.

### 5.2 Tests de features

**Cible** : `features/` (add-transaction, reconcile-bank, settle-debt, link-bank-account, propose-savings-goal, configure-share-request, confirm-mcp-action).

**Outils** : Vitest, Testing Library, MSW (Mock Service Worker) pour mocker les appels API.

**Approche** : tests d'interaction de bout en bout d'une feature, depuis le clic utilisateur jusqu'à l'effet observable, avec API mockée par MSW au niveau réseau (réutilise les schémas OpenAPI). Pas de mock manuel des fonctions de fetch.

### 5.3 Mocking PowerSync côté client

PowerSync ne se teste pas — c'est leur job. Ce qu'on teste, c'est le comportement de notre app face à différents états du SDK.

**Stratégie** : un `MockPowerSyncDatabase` dans `tests/mocks/powersync.ts` qui expose la même surface API que `PowerSyncDatabase` mais s'appuie sur une queue de mutations en mémoire et un état synchronisable manuellement (helpers `simulateOffline()`, `simulateReconnect()`, `simulateSyncedFromServer(rows)`, `simulateWriteResultError(code)` pour tester la gestion des `validation_error` / `immutable_field_violation` côté client — cf. ADR 0014).

**Usage** : tous les tests de features qui dépendent de PowerSync utilisent cette mock. Les tests bout en bout réels sont réservés à Playwright (§6).

### 5.4 Tests SSE côté client

Le wrapper `lib/sse/` (cf. ADR 0012) gère l'authentification short-lived JWT, le `Last-Event-ID` resume, la reconnexion.

**Tests** : MSW intercepte les requêtes SSE et simule différents scénarios — disconnect transitoire, expiration du JWT 5min en cours de flux, événements buffered re-diffusés après reconnect.

---

## 6. End-to-end avec Playwright

### 6.1 Principe et coût

Playwright est utilisé exclusivement pour valider des **chaînes de valeur business complètes** non couvertes par les couches inférieures. Cinq parcours, pas un de plus. Chaque parcours coûte 1-2 jours d'écriture initiale et ~20-30% de son temps en maintenance annuelle.

**Plateformes ciblées** : PWA Web (Chromium) + Chrome Android émulé via Playwright. Pas de tests sur application Capacitor compilée (trop fragile pour de l'E2E).

### 6.2 Les 5 parcours

| # | Parcours | Couvre |
|---|---|---|
| 1 | Onboarding multi-user | `/setup` bootstrap + login + RBAC + setup multi-user (création comptes personnels + commun + invitation + acceptation invitation) |
| 2 | Sync offline → online (golden path) | PowerSync, write upload handler ADR 0014, convergence multi-device, validation_error visible côté client |
| 3 | Reconciliation locale ↔ bancaire | Import OFX (ADR 0009), matching `MatchScorer`, validation, audit trail, dépointage avec Reconciliation entité distincte (ADR 0006) |
| 4 | Cycle de dette complet | Création dette via `share_request` + via overflow F10 (`debt_generation_override`), settlement multi-line nettage croisé, invariant zero-sum vérifié à chaque étape (ADR 0011) |
| 5 | Confirmation action MCP | PAT `read_write` propose une action, push notification (mockée), SSE temps-réel sur web (mocké), écran de confirmation, `modify_then_confirm` créant une entité dérivée avec lineage (ADR 0004) |

**Parcours 2 en détail** (smoke test du stack complet) :

- Login user A sur device 1
- `page.context().setOffline(true)`
- Saisie de 3 transactions
- Vérification : transactions visibles en local
- `page.context().setOffline(false)`
- Attente de la sync (polling sur état)
- Vérification serveur (via API admin de test)
- Ouverture sur device 2 (même user)
- Vérification : les 3 transactions sont présentes
- Tentative d'édition d'un champ gelé sur transaction `confirmed` → `WriteResult.error: immutable_field_violation` visible, mutation purgée

---

## 7. Stratégie PowerSync transversale

Trois niveaux distincts qui ne se substituent pas l'un à l'autre, alignés sur le contrat write upload handler (ADR 0014) :

| Niveau | Cible | Outils | Couverture visée |
|---|---|---|---|
| 1 — Server-side | Write upload handler (ADR 0014) | pytest + testcontainers | **Exhaustive** |
| 2 — Client mocké | Hooks, features | Vitest + MockPowerSyncDatabase | Sélective |
| 3 — Bout en bout | Convergence multi-device | Playwright + PowerSync Service en testcontainer | Un seul golden path (parcours 2) |

**Le niveau 1 porte l'essentiel de la confiance**, parce que c'est server-authoritative : la logique d'arbitrage des conflits vit côté serveur. Propriétés vérifiées :

- **Idempotence** : rejouer la même mutation N fois (même `client_request_id`) = même état final.
- **Ordering préservé dans le batch** : dépendances entre mutations respectées (création compte avant transaction sur ce compte).
- **Convergence** : pour toute permutation valide d'un batch, l'état final converge selon la séquence ordering préservée.
- **Isolation cross-user** : une mutation d'Alice ne peut jamais affecter le compte de Bob (auth + RBAC dans la séquence ADR 0014).
- **Aggregate immutable** : édition d'un champ gelé d'une transaction `confirmed` → `WriteResult.error: immutable_field_violation`, état serveur inchangé (ADR 0001).
- **Matérialisation synchrone des dettes** : après write d'une transaction sur compte commun avec overflow, la table `debts` reflète la projection cohérente dans la même transaction DB (ADR 0002).

Hypothesis a sa place sur ces propriétés. Une stratégie qui génère des séquences de mutations aléatoires sur un même set d'entités, et vérifie que tous les ordres possibles convergent vers le même état, est un excellent test de robustesse.

---

## 8. Factories et fixtures

Trois ergonomies cohabitent, chacune avec un périmètre net :

| Catégorie | Outil | Localisation | Usage |
|---|---|---|---|
| Entités SQLAlchemy | factory-boy + SQLAlchemyModelFactory | `tests/factories/sqlalchemy.py` | Tests d'intégration DB |
| Modèles Pydantic du domaine | Builders maison (fonctions) | `tests/factories/domain.py` | Tests unitaires de domaine |
| Stratégies génératives | Hypothesis | `tests/strategies.py` | Property-based testing |

**Règle de cohérence** : `UserFactory.create()` (SQLA) et `make_user()` (domain) doivent produire des entités équivalentes pour les attributs partagés. Les builders domain consomment les factories SQLA quand nécessaire ; jamais l'inverse.

**Fixtures de données externes** :

```
tests/fixtures/
  enable_banking/
    accounts_list_sg.json
    transactions_page_1.json
    error_session_expired.json
  ofx/
    livret_a_2026_q1.ofx              # OFX 1.x SGML windows-1252
    pel_2025_2026.ofx                 # OFX 1.x SGML UTF-8 BOM
    boursorama_export_2026.ofx        # OFX 2.x XML
    fitid_unstable_societe_generale.ofx
    account_not_yet_linked.ofx
    libelles_accentues_windows_1252.ofx
```

Toutes les fixtures JSON Enable Banking sont validées par les modèles Pydantic générés depuis l'OpenAPI au chargement, pour garantir leur validité.

**Note SQLAlchemy 2 async + factory-boy** : l'intégration async n'est pas native dans factory-boy. Solution retenue : wrapper async dans la fixture `db_session` qui appelle `factory.create()` dans un contexte de session avec commit/rollback explicite. ~30 lignes dans `conftest.py`.

---

## 9. Pipeline CI/CD

Quatre étages avec budgets temps stricts :

### 9.1 Pre-commit (local, instantané)

Hooks via le framework `pre-commit` :

- `ruff` (lint + format)
- `mypy` ou `pyright` sur le diff
- `eslint` + `prettier` côté frontend
- Tests unitaires Python sur fichiers modifiés uniquement

**Budget** : 5-15 secondes. Au-delà, l'usage devient antagoniste et tu contourneras.

### 9.2 Push CI (chaque push, < 5 min)

GitHub Actions, jobs parallèles :

| Job | Contenu |
|---|---|
| backend-lint | ruff, mypy, **import-linter (5 contrats ADR 0005)** |
| backend-unit | pytest unit/ + Hypothesis (max_examples=50) |
| backend-integration | pytest integration/ + testcontainers Postgres |
| backend-http | pytest http/ + httpx ASGI |
| backend-sync | **pytest sync/ : write upload handler exhaustif (ADR 0014)** |
| backend-migrations | Niveau 1 — schema check |
| backend-banking-contract | Niveaux A + B (fixtures uniquement) |
| frontend-lint | eslint, prettier, tsc |
| frontend-unit | vitest run |
| frontend-build | vite build + capacitor sync |

**Objectif** : < 5 min total via parallélisation.

### 9.3 Nightly CI (1x/jour, 30-45 min toléré)

Tout le push CI ré-exécuté plus :

- Property tests avec `max_examples=500`
- Playwright E2E sur les 5 parcours (Chromium + Chrome Android émulé)
- Test contract Enable Banking niveau C (appels API réels)
- Tests de migration Alembic niveau 2 (backfills)
- Audit deps (`pip-audit`, `npm audit`)
- Couverture (coverage.py + Vitest coverage), publication en rapport

### 9.4 Release CI (sur tag git)

Tout le nightly plus :

- Build APK signé via Capacitor
- Génération changelog automatique
- Création GitHub Release
- Notification (Discord, Sentry, peu importe)

---

## 10. Cibles de couverture et métriques

**Couverture par couche** :

| Périmètre | Cible | Mesure |
|---|---|---|
| `modules/*/domain.py` | ≥ 90% lignes + ≥ 80% branches | coverage.py |
| `modules/*/service.py` | ≥ 70% lignes | coverage.py |
| `modules/banking/providers/` | ≥ 85% lignes | coverage.py |
| `modules/sync/` (write upload handler) | ≥ 95% lignes + branches | coverage.py |
| `modules/mcp/` (heuristiques, lineage) | ≥ 85% lignes | coverage.py |
| Endpoints HTTP | 100% des routes ont au moins 1 test (happy + 1 erreur) | comptage manuel |
| `components/business/` | ≥ 75% lignes | Vitest coverage |
| `features/` | ≥ 65% lignes | Vitest coverage |
| Parcours E2E | 5 parcours green sur PWA + Android émulé | Playwright report |

**Métriques de santé** suivies dans le temps :

- Temps total push CI (alerte si > 6 min)
- Temps total nightly CI (alerte si > 50 min)
- Nombre de tests flaky par mois (alerte si > 3)
- Couverture (alerte si baisse > 2 points entre deux releases)
- **Nombre de violations import-linter ignorées** (cible : 0, anti-pattern absolu)

---

## 11. Outils — tableau récapitulatif

| Domaine | Outil | Version cible 2026 |
|---|---|---|
| Test runner Python | pytest | 8.x |
| Async support | pytest-asyncio | 0.24.x |
| Property-based | Hypothesis | 6.x |
| Couverture Python | coverage.py + pytest-cov | 7.x / 5.x |
| Conteneurs de test | testcontainers-python | 4.x |
| HTTP test client | httpx | 0.27.x |
| Factories | factory-boy | 3.x |
| Architecture | **import-linter (5 contrats, cf. §4.3)** | 2.x |
| Lint Python | ruff | latest |
| Type check Python | mypy ou pyright | latest |
| Test runner JS | Vitest | 2.x |
| Component testing | @testing-library/react | 16.x |
| API mocking | MSW (Mock Service Worker) | 2.x |
| E2E | Playwright | 1.4x |
| Pre-commit hooks | pre-commit framework | 4.x |
| CI | GitHub Actions | n/a |

---

## 12. Anti-patterns à éviter

- **Tester l'implémentation au lieu du comportement.** Pas d'introspection des attributs privés, pas de tests sur le nombre d'appels à une fonction interne.
- **Mocker SQLAlchemy.** Si tu sens le besoin de mocker une session DB, c'est que tu testes au mauvais niveau. Soit c'est un test de domaine pur (et il ne touche pas SQLA), soit c'est un test d'intégration (et il utilise testcontainers).
- **Property tautologique.** Reformuler l'implémentation comme propriété sans la tester. Ex. interdit : `assert money.add(other).amount == money.amount + other.amount`. Permis : `assert money.add(other).amount == other.add(money).amount` (commutativité).
- **Désactiver import-linter à la première violation.** Si une règle gêne, c'est soit la règle qui est mal calibrée (corriger la règle), soit l'architecture qui dérive (corriger le code). Pas de `# noqa: contract-N` qui s'accumulent.
- **Doubler les tests unitaires et intégration sur la même logique.** Si une règle est couverte au niveau domaine, ne pas la re-tester au niveau service ou endpoint. Tester ce qui est propre à la couche.
- **Tests E2E qui dupliquent les tests d'intégration.** Un E2E coûte 50x un test d'intégration.
- **Mocker PowerSync au niveau SDK pour des tests serveur.** Le serveur ne voit pas le SDK, il voit des mutations HTTP. Tester le write upload handler avec des payloads JSON directs.
- **Tests sur les schémas Pydantic d'API.** Le typage les couvre.
- **Property-based testing sur des effets de bord.** Hypothesis sur une fonction qui écrit en DB = flaky garanti.
- **Mocker `BankingProvider` à la place de `BankingReader` pour les consommateurs cross-module.** Le runtime production interdit déjà via import-linter ; les tests doivent mocker `BankingReader`.

---

## 13. Roadmap d'implémentation

Ordonnée pour s'inscrire dans la roadmap d'implémentation globale ([`Sans titre.md §6`](./Sans%20titre.md#6-phasing-suggéré)).

### MVP bootstrap (semaine 1-2)

- [ ] Installer pytest, pytest-asyncio, Hypothesis, coverage, testcontainers-python, factory-boy, **import-linter** (avec les 5 contrats §4.3 dès J1).
- [ ] Créer `tests/conftest.py` avec fixtures `db_session`, `client`.
- [ ] Créer `.pre-commit-config.yaml` avec ruff + mypy.
- [ ] Premier test bidon `tests/unit/test_smoke.py` pour valider le pipeline.
- [ ] `.github/workflows/push.yml` et `nightly.yml` avec les jobs définis §9.

### MVP modules à domain

- [ ] Pour le module `transactions` (premier module traité) : structure de test complète comme archétype
    - `tests/unit/domain/test_transactions.py` (TDD, property-based, invariant aggregate immutable ADR 0001)
    - `tests/integration/transactions/test_service.py`
    - `tests/factories/sqlalchemy.py` (TransactionFactory)
    - `tests/factories/domain.py` (make_transaction)
    - `tests/strategies.py` (transaction_strategy, money_strategy, balanced_splits_strategy)
- [ ] Réplication du pattern sur `debts` (ADR 0002 projection + ADR 0011 Settlement), `reconciliation` (ADR 0006), `forecasting`.
- [ ] **Module `sync` write upload handler** (ADR 0014) couvert exhaustivement.

### MVP Enable Banking (OFX d'abord, Enable en V1)

- [ ] Génération du client Pydantic depuis l'OpenAPI Enable Banking avec `datamodel-code-generator`.
- [ ] Tests OFX (`ofxparse` + wrapper, ADR 0009) avec les 6 fixtures cibles §8.
- [ ] Tests Enable Banking niveau A + B en push CI (préparé même si Enable est en V1).

### V1 client

- [ ] Installer Vitest, Testing Library, MSW.
- [ ] Créer `tests/mocks/powersync.ts` avec les helpers ADR 0014.
- [ ] Tests unitaires des `components/business/`.
- [ ] Tests features avec MSW.
- [ ] Tests SSE wrapper avec MSW (ADR 0012).

### V1 qualité

- [ ] Installer Playwright + browser binaries en CI.
- [ ] Écrire les 5 parcours E2E (§6.2).
- [ ] Nightly CI complet (contract Enable Banking niveau C, migrations niveau 2).
- [ ] Couverture publiée, métriques de santé exposées.

### Production

- [ ] Runbook SCA Enable Banking 180 jours.
- [ ] Runbook restore + migration sur dump prod (niveau 3).
- [ ] Runbook reset 2FA (ADR 0013).
- [ ] Runbook recurring rules cron heure (ADR 0007).
- [ ] Premier passage du test de restore complet validé.

---

## 14. Annexe — Synthèse des décisions de test

| # | Sujet | Décision | ADR lié |
|---|---|---|---|
| 1 | Philosophie | Pyramide enrichie d'intégration DB substantielle, pas de testing trophy pur | — |
| 2 | TDD | Strict sur les 5 modules à `domain.py` (`transactions`, `reconciliation`, `debts`, `forecasting`, `mcp`), libre ailleurs | — |
| 3 | Property-based | Hypothesis dès J1, scope = `domain.py` + `shared/` + write upload handler `sync` | 0001, 0002, 0011, 0014 |
| 4 | Stratégie PowerSync | 3 couches : exhaustif serveur (write upload handler ADR 0014), mocké client, 1 E2E | 0014 |
| 5 | Tests d'architecture | **5 contrats import-linter** (layers, internals forbidden, shared isolated, banking provider isolated, mcp consumer-only), J1 | 0004, 0005, 0009 |
| 6 | Contract Enable Banking | Unitaires + fixtures en push CI ; appels réels en nightly sur compte dédié | 0009 |
| 7 | Parcours Playwright | 5 : onboarding multi-user, sync offline→online, reconciliation, cycle dette, confirm action MCP | 0001, 0004, 0006, 0011, 0014 |
| 8 | Factories | factory-boy SQLA + builders Pydantic + Hypothesis strategies | — |
| 9 | CI | Pre-commit local + Push < 5 min + Nightly 30-45 min + Release sur tag | — |
| 10 | Migrations Alembic | Niveau 1 systématique (push CI), Niveau 2 sur backfills (nightly), Niveau 3 manuel avant release | — |
| 11 | Write upload handler | Couverture exhaustive (cible 95%+) sur le contrat 10 étapes | 0014 |
| 12 | MCP heuristiques | Hypothesis property : désactivation auto uniquement sur signaux binaires | 0004, 0013 |

---

## 15. Principe directeur

> **La stratégie de test est l'extension naturelle de l'architecture modulaire** : on protège fort les invariants des 5 modules à `domain.py`, on protège raisonnablement les services, on protège **mécaniquement la structure d'import via 5 contrats import-linter**, on n'investit pas dans les CRUD.
>
> Le but n'est pas la couverture maximale mais la **confiance maximale par unité de temps de maintenance**. Une suite de tests qui tourne en 5 minutes et qui te permet de refactorer agressivement le module `transactions` sans crainte est meilleure qu'une suite à 95% de couverture qui tourne en 25 minutes et que tu désactives en local.

**Test de validation à 6 mois** : si Claude Code propose un refactor important sur le module `transactions` et que la suite de tests passe sans intervention manuelle, l'architecture de test tient. Si tu dois relire 200 lignes pour valider que rien n'est cassé → signal d'alerte sur la qualité des tests, pas sur le refactor.
