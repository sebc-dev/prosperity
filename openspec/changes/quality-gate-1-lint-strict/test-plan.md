## Niveaux

Ce change livre de la **configuration d'outillage**, pas du code applicatif : le « système sous test »
est une commande (`npm run analyse`, `uv run ruff check .`, `uv run deptry .`) et son code de sortie.
Un seul niveau compte : **contrat de commande** — la commande, jouée sur une entrée connue, sort avec
le code et la remontée attendus. Ni unité ni bout-en-bout applicatifs.

## Oracle

Par scénario de la spec, l'oracle est **la sortie réelle de l'outil sur une fixture fautive** :

- Scénarios « … remonté / sort en échec » : un fichier fixture qui enfreint la règle visée, hors du
  périmètre linté par défaut (`client/tests/lint-fixtures/`, `tests/lint_fixtures/`), passé
  explicitement à la commande (`npx eslint --config eslint.config.analyse.js <fixture>` ; `uv run ruff
  check <fixture>`) → code ≠ 0 **et** la règle nommée dans la sortie (`--format json` pour l'asserter).
- Scénarios « base propre / silencieux » : la commande sur `src/` (resp. `backend/`) → code 0.
- Scénarios de sévérité (`quality.json`) : lecture du JSON + la sortie de la commande sur `main` au
  moment de l'ajout — c'est une **preuve capturée**, pas un test rejouable (mode `observé`).
- `check:agent` : le script joué sur une base avec remontées → fichier présent, code 0, `git status`
  vide sur `client/reports/`.
- Docs : présence des lignes attendues dans `docs/ci.md` / `runbooks/ci.md` (`grep`), mode `observé`.

Les fixtures sont des tests **nommés par critère** (`SC-<NN><lettre>`) quand ils sont rejouables par
`vitest`/`pytest` (un test qui `spawn` la commande sur la fixture et asserte la sortie JSON) — c'est la
forme qui rend le mode `test` possible sur P18.2.1 et P18.2.2.

## Cas limites

- Seuils : complexité cognitive **exactement 15** (passe) vs 16 (échoue) ; mccabe 10 vs 11.
- Un fichier de test qui enfreint une règle **éteinte** sur `tests/**` → silence ; le même code dans
  `src/` → remontée (partition production / test).
- Artefact généré (`routeTree.gen.ts`, `schema.d.ts`) fautif → silence.
- Import de frontière : `lib → components/business` (interdit, `warn`) vs `pages → components/business`
  (autorisé) ; import via l'alias `@/` résolu comme un chemin relatif.
- `deptry` : extra (`pyjwt[crypto]`) importé sous un autre nom de module → `per_rule_ignores` motivé.

## Doubles

Aucun. Les outils sont joués réellement ; un double d'ESLint ou de Ruff ne prouverait rien.

## Zones sans test automatisé

- La **sévérité par la mesure** (arriéré sur `main` au moment de l'ajout) et le **budget de gate** :
  preuve observable capturée dans la PR (`observé`).
- Les **diagnostiqueurs** générés (`quality-agents`) : leur comportement se constate au premier run de
  ticket qui les invoque, pas ici (`humanCheckRequired` : relire le bloc d'instructions).
- La mise à jour de `docs/ci.md` / `runbooks/ci.md` (`observé`, `grep`).
