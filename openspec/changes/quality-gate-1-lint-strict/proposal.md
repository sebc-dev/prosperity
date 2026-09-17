## Why

La quality gate du cycle `run` (`.claude/quality.json`, 8 checks) ne mesure que le style, les types et
une couverture sans seuil : elle laisse passer ce que SonarQube attrape — complexité cognitive,
fonctions et branches dupliquées, promesses non attendues hors `recommendedTypeChecked`, hooks React
mal déclarés, accessibilité, dépendances Python fantômes ou inutilisées. Le rapport de recherche du
2026-09-12 ([`docs/recherches/…`](../../../docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md))
et le montage de `colibri-cms` montrent que le **lint statique rapide et déterministe** couvre déjà
ces familles, sans serveur. Sert **EPIC-18 / STORY-S18.2** (étape 1 du rapport ; S18.3 et S18.4 —
code mort/duplication, mutation — sont des changes séparés). Comportement produit servi : aucun
directement ; c'est le filet qui protège les tickets écrits par des agents (principe 2 de
`docs/Stratégie de tests.md`).

## What Changes

- **Frontend — nouvelle passe `analyse`** : un `client/eslint.config.analyse.js` séparé, une
  intention par fichier comme `colibri-cms` — typescript-eslint `stylisticTypeChecked` par-dessus
  le `recommendedTypeChecked` existant, un sous-ensemble d'`eslint-plugin-sonarjs`
  (`cognitive-complexity` à 15, `no-identical-functions`, `no-duplicate-string`,
  `no-duplicated-branches`, `no-collapsible-if`, `no-redundant-boolean`, `no-inverted-boolean-check`,
  `prefer-immediate-return`), `eslint-plugin-jsx-a11y`, et `eslint-plugin-boundaries` sur les zones
  `app` / `pages` / `features` / `components/business` / `components/ui` / `hooks` / `lib`.
- **Frontend — `eslint.config.js` (style, bloquant)** monte `eslint-plugin-react-hooks` en v6
  (`configs.flat.recommended`, règles du React Compiler).
- **Backend — Ruff** : `select` étendu de `C90 SIM RET PERF PT` (+ `W`), `[tool.ruff.lint.mccabe]
  max-complexity = 10`, `per-file-ignores` de `tests/**` calibrés sur mesure.
- **Backend — `deptry`** en dépendance de dev : dépendances manquantes, inutilisées, transitives.
- **`.claude/quality.json`** : deux checks neufs — `frontend-analyse` (cmd `npm run analyse`) et
  `backend-deps` (cmd `uv run deptry .`) — chacun avec son diagnostiqueur `quality-<id>` ; les
  checks existants `frontend-lint` / `backend-lint` conservent leur commande (leur périmètre de
  règles s'élargit par la config).
- **Sévérité par mesure** : un check neuf entre `blocking` si son arriéré est nul après calibrage,
  sinon `advisory` avec l'arriéré consigné et sa condition de promotion (une ligne dans
  `quality.json`). `boundaries` reste **en avis** tant qu'aucun ADR ne contraint `client/src/`
  (`docs/architecture.md` § Frontend : « un écart est une suggestion, pas un bloquant »).
- **Docs** : `docs/ci.md` (commandes par stack, cap lu par `ticket-briefer`) et `runbooks/ci.md`
  (ce qui bloque une PR) à jour ; les scripts `npm run analyse` / `check:agent` documentés.
- **Hors périmètre** : knip, jscpd, vulture, complexité cognitive Python (S18.3) ; Stryker, mutmut
  (S18.4) ; l'applier du projet (`/scd-spec-dev:quality-agents`, commande, pas un change) ;
  résorber l'arriéré que la passe révèle dans `src/` ou `backend/` au-delà de ce qui rend un check
  vert (chaque constat réel devient un ticket ou une fiche, pas un effet de bord ici) ; la CI
  GitHub, qui reste le juge final et n'accueille aucun check nouveau (colibri : la gate du cycle est
  le bon endroit, promouvoir un garde CI touche trois surfaces).

## Capabilities

### New Capabilities
- `quality-gate` : la gate déterministe du cycle `run` — ce qu'elle joue par stack, la sévérité de
  chaque check et la règle qui la fixe, le calibrage des tests, la sortie lisible par un agent, et
  la frontière avec la CI. Première spec de cette capacité ; S18.3 et S18.4 la modifieront.

### Modified Capabilities
- (aucune — `dashboard` n'est pas touchée ; aucune spec vivante ne décrit la gate aujourd'hui.)

## Impact

- **Code** : `client/eslint.config.analyse.js` (neuf), `client/eslint.config.js`,
  `client/package.json` (scripts `analyse`, `check:agent` ; deps `eslint-plugin-sonarjs`,
  `eslint-plugin-jsx-a11y`, `eslint-plugin-boundaries`, `eslint-import-resolver-typescript`,
  `eslint-plugin-react-hooks` ^6), `pyproject.toml` (`[tool.ruff.lint]`, `[tool.ruff.lint.mccabe]`,
  `deptry` dans le groupe dev, `[tool.deptry]`), `uv.lock`, `package-lock.json`.
- **Gate** : `.claude/quality.json` (+2 checks), `.claude/agents/quality-frontend-analyse.md`,
  `.claude/agents/quality-backend-deps.md` (générés par `/scd-spec-dev:quality-agents`).
- **Docs** : `docs/ci.md`, `runbooks/ci.md`, `docs/roadmap/E18-devx-ci.md`.
- **Risque** : les règles type-aware et sonarjs peuvent révéler des défauts réels dans le code
  existant (colibri : une comparaison toujours vraie, un `reduce` sans valeur initiale, trouvés
  dès la première passe). Ils sont **consignés**, pas corrigés en douce ; un check qui les révèle
  entre en avis. Aucun changement de comportement applicatif, aucune API, aucune donnée.
- **Coût** : la passe type-aware type le projet comme `tsc` — quelques secondes ici (colibri :
  ~3 s sur un fichier, ~10 s la boucle complète). Le budget total de la gate est mesuré au ticket et
  consigné dans `docs/ci.md`.
