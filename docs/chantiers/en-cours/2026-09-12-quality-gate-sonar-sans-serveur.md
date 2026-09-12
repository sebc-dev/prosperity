# Quality gate — boucle « Sonar sans serveur » sur les deux stacks

Portée : socle
Ouvert le 2026-09-12 · Actualisé le 2026-09-12 · branche `chore/change-quality-gate-1` · HEAD `e063134`

## Objectif
Réviser `.claude/quality.json` pour que la gate du cycle `run` mesure ce que SonarQube mesure (bugs,
smells, complexité cognitive, duplication, code mort) — sans serveur — sur le frontend React 19/TS et
le backend Python, et qu'un défaut dans un test neuf cesse de bloquer les tickets.

## Contexte à charger
à lire      `.claude/quality.json` — la gate : 8 checks, 8 diagnostiqueurs, pas d'applier (66 l.)
à lire      `openspec/changes/quality-gate-1-lint-strict/proposal.md` — l'étape 1 cadrée ; son
            « Hors périmètre » borne ce que ce chantier garde à sa charge (71 l.)
à situer    `openspec/changes/quality-gate-1-lint-strict/design.md` — décisions, configs adaptées aux
            chemins réels, plan P18.2.1→3 ; c'est `tickets` qui le lit, pas la reprise
à situer    `docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md` — le rapport ; ses étapes 2
            et 3 (knip/jscpd/vulture, mutation) attendent les changes S18.3/S18.4
à situer    `~/projets/colibri-cms/eslint.config.analyse.js` — le patron cité par le proposal ; pour
            l'implémenteur du ticket frontend, pas pour la reprise
à situer    `~/projets/colibri-cms/.claude/quality.json`, `docs/ci.md` › « La boucle locale d'analyse »
            — le montage de référence, conclusions déjà ici
à situer    `docs/chantiers/en-cours/2026-09-11-run-budget-summary-03.md` — visible sur
            `impl/budget-summary-03` seulement ; le ticket que cette gate bloque

## Acquis
- J'ai fait tourner une recherche (rapport ci-dessus) à partir de la boucle de `colibri-cms` : trois
  configs ESLint séparées (style / frontières / analyse type-aware + sonarjs), `jscpd` en baseline
  `origin/main`, `knip` en avis, Stryker hors gate sur un timer (ADR-0013 de colibri : la mutation,
  pas la couverture, mesure la profondeur des tests).
- Points durs vérifiés : seul `flake8-cognitive-complexity` (0.1.0, peu maintenu) porte la vraie
  complexité cognitive en Python — Ruff `C901`/radon/xenon sont cyclomatiques ; Ruff ne fait pas la
  taint analysis inter-fichiers de Sonar ; Stryker + vitest incrémental a un bug de baseline non
  déterministe (#6004) ; testcontainers impose des conteneurs session-scoped avant toute mutation.
- J'ai inversé l'ordre prévu : le change de l'étape 1 est ouvert AVANT l'applier, et j'ai laissé
  l'applier hors du change à dessein — c'est un geste de commande (`/scd-spec-dev:quality-agents`),
  pas une capacité. Le ticket 03 reste bloqué par un `TS18048` dans un test neuf tant qu'il n'est
  pas posé.

## Prochaine étape
Deux gestes indépendants, dans cet ordre : poser l'applier (`/scd-spec-dev:quality-agents` — débloque
le ticket 03), puis découper le change (`/scd-spec-dev:tickets quality-gate-1-lint-strict`, le plan
P18.2.1→3 est déjà dans le design). La mesure du bruit se fait au ticket, pas avant.

## Écarté
- SonarQube/SonarCloud en gate PR — serveur, et la taint analysis est Enterprise.
- La mutation en check bloquant — coût, et bug de baseline ; timer nocturne comme colibri.
- radon/xenon comme mesure « cognitive » — cyclomatiques seulement.
- `strictTypeChecked` d'emblée sur ce dépôt — le rapport le réserve aux équipes TS aguerries et le
  classe hors semver ; colibri l'a pris parce que `src/` y fait 3 248 lignes. À mesurer ici avant.
- jscpd cross-langage TS↔Python — pools séparés voulus.
