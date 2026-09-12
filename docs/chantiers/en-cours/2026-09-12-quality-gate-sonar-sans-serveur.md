# Quality gate — boucle « Sonar sans serveur » sur les deux stacks

Portée : socle
Ouvert le 2026-09-12 · branche `chore/quality-gate-sonar-sans-serveur` · HEAD `c2a6dac`

## Objectif
Réviser `.claude/quality.json` pour que la gate du cycle `run` mesure ce que SonarQube mesure (bugs,
smells, complexité cognitive, duplication, code mort) — sans serveur — sur le frontend React 19/TS et
le backend Python, et qu'un défaut dans un test neuf cesse de bloquer les tickets.

## Contexte à charger
à lire      `.claude/quality.json` — la gate : 8 checks, 8 diagnostiqueurs, pas d'applier (66 l.)
à extraire  `docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md` › `## Recommendations` —
            les trois étapes et les conditions de bascule ; le reste est distillé ci-dessous
à extraire  `docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md` › blocs `eslint.config.mjs`,
            `knip.json`, `.jscpd.json`, `pyproject.toml` — les configs de départ, à adapter aux chemins réels
à lire      `~/projets/colibri-cms/eslint.config.analyse.js` — le patron d'une passe type-aware séparée
            et son calibrage `tests/**` motivé ligne à ligne (75 l.)
à situer    `~/projets/colibri-cms/.claude/quality.json`, `docs/ci.md` › « La boucle locale d'analyse »
            — le montage de référence, conclusions déjà ici
à situer    `docs/chantiers/en-cours/2026-09-11-run-budget-summary-03.md` — le ticket que cette gate bloque

## Acquis
- J'ai fait tourner une recherche (rapport ci-dessus) à partir de la boucle de `colibri-cms` : trois
  configs ESLint séparées (style / frontières / analyse type-aware + sonarjs), `jscpd` en baseline
  `origin/main`, `knip` en avis, Stryker hors gate sur un timer (ADR-0013 de colibri : la mutation,
  pas la couverture, mesure la profondeur des tests).
- Ordre retenu par le rapport : (1) **bloquant tout de suite** — typescript-eslint `recommendedTypeChecked`
  + `stylisticTypeChecked`, react-hooks 6, jsx-a11y, sous-ensemble sonarjs (`cognitive-complexity@15`,
  `no-identical-functions`, `no-duplicate-string`), `eslint-plugin-boundaries` ; Ruff `C90 PLR SIM RET
  PERF PT` + `deptry` ; (2) **en avis** — knip (après `routeTree.gen.ts`), jscpd baseline, vulture,
  flake8-cognitive-complexity ; (3) **hors gate** — StrykerJS vitest-runner, mutmut 3.
- Points durs vérifiés : seul `flake8-cognitive-complexity` (0.1.0, peu maintenu) porte la vraie
  complexité cognitive en Python — Ruff `C901`/radon/xenon sont cyclomatiques ; Ruff ne fait pas la
  taint analysis inter-fichiers de Sonar ; Stryker + vitest incrémental a un bug de baseline non
  déterministe (#6004) ; testcontainers impose des conteneurs session-scoped avant toute mutation.
- Le calibrage se décide sur une mesure, pas un principe (colibri : 30× plus de bruit dans les tests
  que dans `src/`) ; un check posé rouge entre en `advisory` et se promeut au vert.
- Le ticket 03 est bloqué par un `TS18048` dans un test neuf que la gate n'a pas le droit d'éditer :
  l'applier du projet (`/scd-spec-dev:quality-agents`, table typecheck/lint/format = mécanique seulement,
  couverture = non) reste la reprise, indépendante de cette révision.

## Prochaine étape
Arbitrer l'ordre : poser l'applier d'abord (débloque 03), puis ouvrir un change (`/opsx:propose`) pour
l'étape 1 — la révision touche `eslint.config.js`, `pyproject.toml`, `quality.json` et huit
diagnostiqueurs, c'est une capacité, pas une fiche. Mesurer le bruit initial avant de fixer une
sévérité.

## Écarté
- SonarQube/SonarCloud en gate PR — serveur, et la taint analysis est Enterprise.
- La mutation en check bloquant — coût, et bug de baseline ; timer nocturne comme colibri.
- radon/xenon comme mesure « cognitive » — cyclomatiques seulement.
- `strictTypeChecked` d'emblée sur ce dépôt — le rapport le réserve aux équipes TS aguerries et le
  classe hors semver ; colibri l'a pris parce que `src/` y fait 3 248 lignes. À mesurer ici avant.
- jscpd cross-langage TS↔Python — pools séparés voulus.
