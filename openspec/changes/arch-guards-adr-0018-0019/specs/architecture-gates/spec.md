## Purpose

La capacité `architecture-gates` est l'ensemble des filets mécaniques qui font échouer le lint ou la
suite unitaire quand un diff viole un invariant **promu** de `docs/architecture.md` (ici A10–A13,
ADR 0018 et 0019) — et qui restent silencieux quand il le respecte. Un invariant opposable sans
garde ne tient que par la review ; cette capacité le fait tenir en CI.

## ADDED Requirements

### Requirement: La zone ui du client n'importe aucun client réseau

Le lint bloquant du client (`npm run lint`, depuis `client/`) SHALL échouer quand un fichier de
production de la zone `ui` — `src/app/`, `src/pages/`, `src/features/`, `src/components/`,
`src/hooks/` — importe `openapi-fetch`, `@powersync/web` ou `@microsoft/fetch-event-source`
(invariant A10, ADR 0018). Le message SHALL nommer la zone `lib` comme la seule autorisée. Les fichiers
de test de la zone `ui` et les paquets de lecture locale `@powersync/react` et
`@powersync/drizzle-driver` SHALL rester libres.

#### Scenario: Hook important le client HTTP typé

- **WHEN** un fichier `src/hooks/*.ts` (hors test) importe `openapi-fetch`
- **THEN** `npm run lint` échoue avec une remontée de sévérité `error` sur la règle
  `no-restricted-imports`, citant le fichier et un message qui renvoie vers `src/lib/`

#### Scenario: Composant important le SDK PowerSync web

- **WHEN** un fichier `src/components/**/*.tsx` (hors test) importe `@powersync/web`
- **THEN** `npm run lint` échoue avec une remontée `error` sur `no-restricted-imports`

#### Scenario: Page important le client SSE

- **WHEN** un fichier `src/pages/*.tsx` (hors test) importe `@microsoft/fetch-event-source`
- **THEN** `npm run lint` échoue avec une remontée `error` sur `no-restricted-imports`

#### Scenario: Test de la zone ui exempté

- **WHEN** un fichier `src/app/*.test.tsx` importe un type de `@powersync/web`
- **THEN** `npm run lint` ne remonte rien pour cet import

#### Scenario: Lecture locale PowerSync libre dans ui

- **WHEN** un fichier `src/hooks/*.ts` importe `@powersync/react` et `@powersync/drizzle-driver`
- **THEN** `npm run lint` ne remonte rien pour ces imports

#### Scenario: La zone lib importe librement les clients réseau

- **WHEN** un fichier `src/lib/**/*.ts` importe `openapi-fetch`, `@powersync/web` ou
  `@microsoft/fetch-event-source`
- **THEN** `npm run lint` ne remonte rien pour ces imports

### Requirement: La zone lib du client n'importe rien de la zone ui

Le lint bloquant du client SHALL échouer quand un fichier de `src/lib/` importe un module de
`src/app/`, `src/pages/`, `src/features/`, `src/components/` ou `src/hooks/` par l'alias `@/`
(invariant A11, ADR 0018). Les imports internes à `lib` (`@/lib/**`) et les imports de `ui` vers `lib`
SHALL rester libres.

#### Scenario: lib important un composant

- **WHEN** un fichier `src/lib/**/*.ts` importe `@/components/ui/button`
- **THEN** `npm run lint` échoue avec une remontée `error` sur `no-restricted-imports`, citant le
  fichier et le chemin importé

#### Scenario: lib important un hook

- **WHEN** un fichier `src/lib/**/*.ts` importe `@/hooks/use-current-user`
- **THEN** `npm run lint` échoue avec une remontée `error` sur `no-restricted-imports`

#### Scenario: lib important lib

- **WHEN** un fichier `src/lib/powersync/*.ts` importe `@/lib/auth/session`
- **THEN** `npm run lint` ne remonte rien pour cet import

#### Scenario: ui important lib

- **WHEN** un fichier `src/pages/*.tsx` importe `@/lib/api/client`
- **THEN** `npm run lint` ne remonte rien pour cet import

### Requirement: Les migrations n'importent des modules que leurs models

La suite unitaire backend (`uv run pytest tests/unit/`) SHALL échouer quand `alembic/env.py` ou un
fichier `alembic/versions/*.py` importe un module `backend.*` hors de l'ensemble admis :
`backend.config`, `backend.shared.models`, `backend.modules.<module>.models` (invariant A13,
ADR 0019). L'échec SHALL citer le fichier et l'import fautif.

#### Scenario: Migration important un service

- **WHEN** un fichier d'`alembic/` contient `from backend.modules.debts.service import …`
- **THEN** la suite unitaire échoue en citant le fichier et `backend.modules.debts.service`

#### Scenario: Migration important une surface publique

- **WHEN** un fichier d'`alembic/` contient `import backend.modules.auth.public`
- **THEN** la suite unitaire échoue en citant le fichier et `backend.modules.auth.public`

#### Scenario: Migration important shared hors models

- **WHEN** un fichier d'`alembic/` contient `from backend.shared.db import get_db`
- **THEN** la suite unitaire échoue en citant le fichier et `backend.shared.db`

#### Scenario: Imports admis

- **WHEN** un fichier d'`alembic/` n'importe de `backend` que `backend.config`,
  `backend.shared.models` et des `backend.modules.<module>.models`
- **THEN** la suite unitaire ne remonte rien pour ce fichier

#### Scenario: Base propre

- **WHEN** l'arborescence `alembic/` est celle du dépôt au moment du change
- **THEN** le test A13 passe

### Requirement: Deux portes vers Postgres, et deux seulement

La suite unitaire backend SHALL échouer quand un fichier Python de `backend/` ou d'`alembic/` autre que
`backend/shared/db.py` et `alembic/env.py` appelle `create_async_engine`, `async_engine_from_config`
ou `create_engine` (invariant A12, ADR 0019). L'échec SHALL citer le fichier et l'appel.

#### Scenario: Module ouvrant son propre engine

- **WHEN** un fichier `backend/modules/<module>/**/*.py` appelle `create_async_engine(...)`
- **THEN** la suite unitaire échoue en citant le fichier et `create_async_engine`

#### Scenario: Script ouvrant une connexion synchrone

- **WHEN** un fichier `backend/scripts/*.py` appelle `create_engine(...)`
- **THEN** la suite unitaire échoue en citant le fichier et `create_engine`

#### Scenario: Les deux portes admises

- **WHEN** `backend/shared/db.py` appelle `create_async_engine` et `alembic/env.py` appelle
  `async_engine_from_config`
- **THEN** la suite unitaire ne remonte rien pour ces deux fichiers

#### Scenario: Mention sans appel

- **WHEN** un fichier de `backend/` ne mentionne `create_engine` que dans une docstring ou un
  commentaire, sans l'appeler
- **THEN** la suite unitaire ne remonte rien pour ce fichier

#### Scenario: Base propre

- **WHEN** l'arborescence `backend/` et `alembic/` est celle du dépôt au moment du change
- **THEN** le test A12 passe
