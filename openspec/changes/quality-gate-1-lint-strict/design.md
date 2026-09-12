## Context

Voir proposal.md — Why. État courant : `client/eslint.config.js` (ESLint 9 flat, typescript-eslint 8
`recommendedTypeChecked` via `projectService`, react-hooks 5, react-refresh, relâchement ciblé sur
`src/components/ui/**`, artefacts générés ignorés) ; `pyproject.toml` Ruff `E F I UP B PL` +
`PGH004 RUF100`, `tests/**` exempté de `PLR2004` ; pyright strict ; import-linter 12 contrats ;
`.claude/quality.json` 8 checks, 8 diagnostiqueurs, pas d'applier. La CI GitHub (`push.yml`) joue
lint/format/types/tests par périmètre, `ci-required` seul check requis (`runbooks/ci.md`).

Contraintes : la gate est jouée par des agents (`quality-analyzer` → diagnostiqueur → triage →
applier), donc chaque check doit sortir en `exit 0`/`≠ 0` net, être rejouable en quelques secondes,
et ne pas éditer un test par autofix (invariant du cycle). `docs/architecture.md` § Frontend : la
structure de `client/src/` n'est contrainte par aucun ADR — « un écart est une suggestion, pas un
bloquant ».

## Goals / Non-Goals

**Goals :**
- Une passe frontend type-aware stricte séparée (`analyse`), mesurée, calibrée sur `tests/**`, puis
  déclarée dans la gate avec la sévérité que la mesure autorise.
- Le lint backend étendu aux familles Sonar que Ruff porte, plus `deptry`, même méthode.
- Diagnostiqueurs et docs alignés, budget de gate mesuré.

**Non-Goals :**
- Résorber l'arriéré révélé au-delà du strict nécessaire pour qu'un check entre vert (chaque constat
  réel → ticket ou fiche).
- Toucher à la CI GitHub, au `scope` de `quality.json` (sans effet, colibri l'a mesuré), à l'applier.
- Complexité cognitive Python, code mort, duplication, mutation (S18.3, S18.4).

## Decisions

- **Deux fichiers ESLint, une intention chacun** — `eslint.config.js` reste le style bloquant
  (`npm run lint`, inchangé hormis react-hooks ≥ 6) ; `eslint.config.analyse.js` porte la passe
  stricte (`npm run analyse`). *Pourquoi* : sévérités et calibrages différents, jouables et
  échouables séparément ; c'est le patron de `colibri-cms` qui a tenu. *Alternative écartée* : tout
  dans `eslint.config.js` (le rapport le propose) — un seul check rouge paralyserait `frontend-lint`,
  aujourd'hui bloquant et vert.
- **`recommendedTypeChecked` + `stylisticTypeChecked`, pas `strictTypeChecked`** — la doc
  typescript-eslint classe `strict-type-checked` hors semver et le réserve aux équipes TS aguerries ;
  colibri l'a pris sur 3 248 lignes de `src/`. Ici : mesurer d'abord (`npx eslint --config
  eslint.config.analyse.js src/ --format json`) ; `strict` est une promotion ultérieure.
- **Sous-ensemble sonarjs nommé, pas `configs.recommended` entier** — les règles à valeur ajoutée
  au-delà de typescript-eslint (rapport § sonarjs) : `cognitive-complexity` (15),
  `no-identical-functions`, `no-duplicate-string` (seuil 5), `no-duplicated-branches`,
  `no-collapsible-if`, `no-redundant-boolean`, `no-inverted-boolean-check`, `prefer-immediate-return`,
  `no-useless-catch`, `max-switch-cases`. *Pourquoi* : sonarjs v4 ne publie que ses règles propres
  mais son `recommended` reste large ; un sous-ensemble se lit et se justifie règle par règle.
- **`boundaries/*` en `warn`, matrice déclarée** — `app → *` ; `pages → features, components/*,
  hooks, lib` ; `features → components/*, hooks, lib` ; `components/business → components/ui, hooks,
  lib` ; `hooks → lib` ; `components/ui`, `lib` → rien (interne à la zone). *Pourquoi `warn`* :
  aucun ADR ne contraint `client/src/` (`docs/architecture.md`) — une règle `error` créerait un
  invariant sans décision. **Proposition d'ADR** (hors de ce change) : « 0018 — frontières de zones du
  client », qui promouvrait ces règles en `error` et la matrice en table d'invariants. Le resolver
  TypeScript (`eslint-import-resolver-typescript`) est requis pour l'alias `@/`.
- **Un check `frontend-analyse` distinct dans `quality.json`** (`cmd: npm --prefix client run
  analyse`, `autofix: null`) plutôt que d'élargir `frontend-lint`. Les règles `stylistic` ont des
  fixes sûrs, mais un autofix ici toucherait les tests (le cas du ticket 02) : on ne l'active pas
  dans ce change ; le `quality-fixer` 0.7.1 sait garder un autofix additif sur un test, à évaluer
  après un premier cycle.
- **Ruff : `select` étendu, `mccabe = 10`, `PT` calibré** — `C90 SIM RET PERF PT W` s'ajoutent à
  `E F I UP B PL`. `PLR` est déjà dans `PL`. `per-file-ignores` de `tests/**` : `PLR2004` (existant)
  + ce que la mesure justifie (`PLR0913`/`PLR0915` sur les fixtures, `PT011` si `match` partout est
  du bruit) — chaque ligne avec son chiffre. Les fixes des familles ajoutées sont tous marqués sûrs
  ou non-appliqués par `--fix` sans `--unsafe-fixes` : l'autofix existant de `backend-lint` reste
  valide.
- **`deptry` en check `backend-deps`** (`uv run deptry .`, `autofix: null`, `[tool.deptry]` :
  `known_first_party = ["backend"]`, `exclude` `.venv|client|htmlcov`, `pep621_dev_dependency_groups
  = ["dev"]`). *Pourquoi deptry et pas vulture ici* : deptry est déterministe et quasi sans faux
  positif ; vulture est bruyant (rapport) → S18.3.
- **`check:agent` frontend** — un script `client/scripts/rapports-analyse.mjs` sur le modèle de
  colibri : joue `analyse` en `--format json --output-file reports/analyse/eslint.json`, imprime un
  digest, rend toujours 0. `client/reports/` ignoré par git. *Pourquoi un script* : une chaîne `&&`
  s'arrête au premier rouge et l'agent n'a qu'un tiers du tableau.
- **Sévérité par la mesure, consignée dans `docs/ci.md`** — règle de la spec ; `quality.json` n'a
  pas de champ libre (contrat `quality-setup`).
- **Diagnostiqueurs** générés par `/scd-spec-dev:quality-agents frontend-analyse` puis
  `backend-deps` ; leurs blocs d'instructions reprennent le patron de `quality-frontend-lint`
  (périmètre = fichiers du ticket, jamais l'arriéré ; dérogation → `applicable:false` + motif).
- **Conformité ADR** : aucun ADR ne contraint l'outillage ; ADR-0002/0014 (backend) ne sont pas
  touchés ; `docs/architecture.md` § Frontend respecté par le choix `warn`.

## Risks / Trade-offs

- [La passe révèle des défauts réels dans `src/` — colibri en a trouvé quatre à la première passe] →
  consignés dans la PR et en tickets ; le check entre `advisory` ; jamais un `eslint-disable` pour
  faire verdir (filet `integrity-reviewer`).
- [`eslint-plugin-react-hooks` ≥ 6 change des règles sur du code existant (React Compiler)] →
  mesurer sur `npm run lint` avant de monter ; si l'arriéré est non nul, monter d'abord en `warn`
  dans `eslint.config.js` et promouvoir au vert.
- [Coût de la passe type-aware] → mesurer (colibri : ~3 s par fichier, ~10 s complet) ; `--cache`
  explicite ; budget total de la gate consigné dans `docs/ci.md`, seuil de révision ~3 min.
- [Bruit `tests/**` 30:1 comme à colibri] → calibrage par extinction motivée chiffrée, uniquement sur
  les tests.
- [`deptry` et les extras `[argon2]`/`[crypto]`/`[standard]`, `psycopg2-binary`, `email-validator`
  importés indirectement] → `per_rule_ignores` motivés dans `[tool.deptry]`.
- [Versions : `eslint-plugin-react-hooks` est en 7.x sur npm, `eslint-plugin-boundaries` 7.x,
  `eslint-plugin-jsx-a11y` 6.10, `eslint-plugin-sonarjs` 4.2, tous compatibles ESLint 9] → figer au
  ticket avec `npm view`, ne pas copier les numéros du rapport.

## Migration Plan

1. P18.2.1 — frontend : deps, `eslint.config.analyse.js`, mesure, calibrage, scripts `analyse` /
   `check:agent`, react-hooks ≥ 6 dans `eslint.config.js`, check `frontend-analyse` dans
   `quality.json` (sévérité par mesure), `docs/ci.md`.
2. P18.2.2 — backend : Ruff `select`, `mccabe`, calibrage `tests/**`, `deptry` + `[tool.deptry]`,
   check `backend-deps`, `docs/ci.md`.
3. P18.2.3 — diagnostiqueurs (`quality-agents`), `runbooks/ci.md`, budget de gate consigné.

Rollback : retirer le check de `quality.json` (une ligne) ; les configs restent jouables à la main.
Aucune surface CI touchée.

## Open Questions

- Aucune qui bloque le découpage. La question « `boundaries` en `error` » est reportée à l'ADR
  proposé ci-dessus, hors de ce change.
