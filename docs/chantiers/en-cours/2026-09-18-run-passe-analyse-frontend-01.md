# Run bloqué — passe `analyse` frontend (ticket 01)

Portée : quality-gate-1-lint-strict · ticket 01
Ouvert le 2026-09-18 · Actualisé le 2026-09-18 · branche `impl/passe-analyse-frontend-01` · HEAD `6aa94f0`

## Objectif
Faire aboutir le run du ticket 01 (config `eslint.config.analyse.js`, deps, tests `SC-01a..g`) jusqu'à
sa PR — statut `blocked-verify` : les 7 critères sont vérifiés, la ceinture `npm run test` ne l'est pas.

## Contexte à charger
à lire      `openspec/changes/quality-gate-1-lint-strict/tickets/01-passe-analyse-frontend.md` — le ticket (60 l.)
à situer    `openspec/changes/quality-gate-1-lint-strict/design.md` — les décisions de la passe
à situer    worktree `.git/scd-worktrees/passe-analyse-frontend-01` — le SEUL exemplaire du travail :
            `client/eslint.config.analyse.js`, `client/tests/lint/analyse.test.ts` (neufs, non suivis),
            `client/package.json` + lock (modifiés) ; rien n'est commité

## Acquis
- Les 7 tests `SC-01a..g` passaient seuls (`npm run test -- tests/lint/analyse.test.ts` : 7/7), via
  `new ESLint({ overrideConfigFile: 'eslint.config.analyse.js' }).lintText(src, { filePath })`.
- La ceinture (`npm run test` complet) a échoué pour deux causes d'environnement, pas de ticket :
  (1) le worktree vit sous `.git/scd-worktrees/` et Vite 8 met `**/.git/**` dans `server.fs.deny`
  par défaut → 36 suites jsdom tombent sur `Cannot find module /tests/setup.ts` (preuve : même suite
  avec `server.fs.deny: []` → 182 passed) ; (2) le binaire natif `better-sqlite3` est absent dans le
  bac à sable (pas de `cc`) → 12 tests drizzle/hooks en `Could not locate the bindings file`.
- La passe `analyse` restait rouge sur `src/` avec 3 remontées d'arriéré, non masquées :
  `src/lib/sse/client.ts:97` cognitive-complexity 28 > 15, `src/lib/powersync/adopt.ts:15`
  no-empty-function, `src/lib/drizzle/schema.test.ts:73` array-type — à consigner dans la PR.

## Prochaine étape
Relancer la vérification hors du bac à sable : depuis le worktree, `cd client && npm ci && npm run
test` sur une machine avec `cc` (ou déplacer le worktree hors de `.git/` : `git worktree move`), puis
commiter et reprendre le run (`/scd-spec-dev:run quality-gate-1-lint-strict 01`) ou pousser et
ouvrir la PR à la main si la ceinture est verte.

## Écarté
- Faire verdir `npm run analyse` sur `src/` dans ce ticket — l'arriéré est le périmètre du ticket 04
  (sévérité par la mesure), jamais un `eslint-disable`.
- Modifier `vite.config.ts` (`server.fs.deny`) pour contourner l'emplacement du worktree — le défaut
  est dans l'outillage du run (worktrees sous `.git/`), pas dans le projet ; à corriger côté plugin
  `scd-spec-dev` (emplacement des worktrees), pas ici.
