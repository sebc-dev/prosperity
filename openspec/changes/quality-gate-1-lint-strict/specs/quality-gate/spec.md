## Purpose

La capacité `quality-gate` est la liste déterministe de checks (`.claude/quality.json`) que le cycle
`run` rejoue sur chaque ticket avant la review : ce que chaque stack joue, la sévérité de chaque check
et la règle qui la fixe, le calibrage des tests, une sortie lisible par un agent, et la frontière avec
la CI qui reste le juge final.

## ADDED Requirements

### Requirement: Passe d'analyse frontend type-aware

Le frontend SHALL exposer une commande `npm run analyse` (depuis `client/`) qui joue une configuration
ESLint **séparée** de celle du style, portant les règles typescript-eslint `recommendedTypeChecked` et
`stylisticTypeChecked`, un sous-ensemble nommé de règles `sonarjs` et les règles d'accessibilité
`jsx-a11y`, sur tous les fichiers `.ts`/`.tsx` de `client/src/` hors artefacts générés.

#### Scenario: Complexité cognitive au-dessus du seuil

- **WHEN** un fichier de `client/src/` (hors tests) contient une fonction dont la complexité
  cognitive dépasse 15
- **THEN** `npm run analyse` sort en échec et la remontée cite le fichier, la ligne, la règle
  `sonarjs/cognitive-complexity` et la valeur mesurée

#### Scenario: Promesse non attendue

- **WHEN** un fichier de `client/src/` (hors tests) appelle une fonction rendant une `Promise` sans
  `await`, `void` ni `.then`/`.catch`
- **THEN** `npm run analyse` sort en échec sur `@typescript-eslint/no-floating-promises`

#### Scenario: Fonctions identiques

- **WHEN** deux fonctions d'un même fichier de `client/src/` (hors tests) ont un corps identique
- **THEN** `npm run analyse` sort en échec sur `sonarjs/no-identical-functions`

#### Scenario: Artefacts générés ignorés

- **WHEN** `src/routeTree.gen.ts` ou `src/lib/api/schema.d.ts` contient une infraction à une règle
  de la passe
- **THEN** `npm run analyse` ne la remonte pas (fichiers hors périmètre)

#### Scenario: Base propre

- **WHEN** aucun fichier de `client/src/` n'enfreint une règle de la passe
- **THEN** `npm run analyse` sort en succès (code 0) sans remontée

### Requirement: Frontières de zones frontend

La passe d'analyse SHALL vérifier le sens des dépendances entre les zones de `client/src/` — `app`,
`pages`, `features`, `components/business`, `components/ui`, `hooks`, `lib` — selon une matrice
déclarée : une zone n'importe que les zones que la matrice lui autorise ; `components/ui` et `lib`
n'importent aucune autre zone.

#### Scenario: Import interdit remonté

- **WHEN** un fichier de `client/src/lib/` importe un module de `client/src/components/business/`
- **THEN** `npm run analyse` remonte l'arête interdite avec la règle `boundaries/element-types`,
  le fichier source et la zone cible

#### Scenario: Import autorisé silencieux

- **WHEN** un fichier de `client/src/pages/` importe un module de `client/src/components/business/`
- **THEN** la passe ne remonte rien pour cette arête

#### Scenario: Frontières en avis tant qu'aucun ADR ne les contraint

- **WHEN** la gate joue le check `frontend-analyse` et qu'aucun ADR de `docs/adr/` ne contraint la
  structure de `client/src/`
- **THEN** une infraction de frontière est remontée comme **avis** (elle n'échoue pas un check
  `blocking` à elle seule) — la sévérité des règles `boundaries/*` est `warn`

### Requirement: Règles React Compiler dans le lint bloquant

Le lint de style frontend (`npm run lint`) SHALL appliquer les règles d'`eslint-plugin-react-hooks`
en version 6 ou ultérieure (`configs.flat.recommended`), qui incluent les règles du React Compiler.

#### Scenario: Hook conditionnel refusé

- **WHEN** un composant de `client/src/` appelle un hook à l'intérieur d'une condition
- **THEN** `npm run lint` sort en échec sur `react-hooks/rules-of-hooks`

#### Scenario: Mutation d'une valeur pendant le rendu refusée

- **WHEN** un composant de `client/src/` mute une prop ou une valeur issue d'un hook pendant le rendu
- **THEN** `npm run lint` sort en échec sur une règle `react-hooks/*` du React Compiler (ex.
  `react-hooks/immutability`)

### Requirement: Lint backend étendu à la complexité et aux idiomes

Le lint backend (`uv run ruff check .`) SHALL appliquer, en plus des familles actuelles, les
familles `C90` (mccabe, seuil 10), `SIM`, `RET`, `PERF`, `PT` et `W`.

#### Scenario: Complexité cyclomatique au-dessus du seuil

- **WHEN** une fonction de `backend/` a une complexité cyclomatique supérieure à 10
- **THEN** `uv run ruff check .` sort en échec sur `C901` en citant la fonction et sa valeur

#### Scenario: Idiome pytest dans un test

- **WHEN** un test de `tests/` utilise `pytest.raises` sans `match` ni type d'exception précis
- **THEN** `uv run ruff check .` remonte `PT011`, sauf si le calibrage `tests/**` l'a explicitement
  éteint avec son motif

#### Scenario: Autofix sûr conservé

- **WHEN** la gate joue l'autofix de `backend-lint` (`ruff check . --fix`)
- **THEN** seules les corrections marquées sûres par Ruff sont appliquées ; aucune règle des
  familles ajoutées n'introduit de correction non sûre

### Requirement: Dépendances Python cohérentes

Le backend SHALL exposer un check `backend-deps` (`uv run deptry .`) qui échoue si une dépendance
déclarée n'est importée nulle part, si un import ne correspond à aucune dépendance déclarée, ou si
un import repose sur une dépendance transitive non déclarée.

#### Scenario: Dépendance déclarée inutilisée

- **WHEN** `pyproject.toml` déclare un paquet qu'aucun module de `backend/`, `alembic/` ou `tests/`
  n'importe
- **THEN** `uv run deptry .` sort en échec en nommant le paquet (`DEP002`)

#### Scenario: Import sans dépendance déclarée

- **WHEN** un module de `backend/` importe un paquet absent de `pyproject.toml` (transitif ou non)
- **THEN** `uv run deptry .` sort en échec en nommant le module et l'import (`DEP001` ou `DEP003`)

#### Scenario: Base propre

- **WHEN** chaque dépendance déclarée est importée et chaque import est déclaré
- **THEN** `uv run deptry .` sort en succès

### Requirement: Sévérité fixée par la mesure

Chaque check de `.claude/quality.json` SHALL porter une sévérité `blocking` ou `advisory`, et un
check nouvellement ajouté SHALL entrer `blocking` seulement si sa commande sort en succès sur la
base au moment de l'ajout ; sinon il entre `advisory`, et l'arriéré mesuré ainsi que la condition de
promotion sont consignés dans `docs/ci.md` (le contrat de `quality.json` n'a pas de champ libre).

#### Scenario: Check neuf vert entre bloquant

- **WHEN** un check est ajouté à `quality.json` et sa commande sort en succès sur `main`
- **THEN** son entrée porte `"severity": "blocking"`

#### Scenario: Check neuf rouge entre en avis avec son arriéré

- **WHEN** un check est ajouté à `quality.json` et sa commande sort en échec sur `main`
- **THEN** son entrée porte `"severity": "advisory"` et `docs/ci.md` donne, pour ce check, le nombre de
  remontées mesuré, la date, et la condition de promotion (« promouvoir `blocking` à 0 remontée »)

#### Scenario: Un check bloquant n'échoue jamais sur l'arriéré

- **WHEN** un ticket ne touche aucun fichier cité par une remontée d'un check `blocking`
- **THEN** ce check sort en succès sur la branche du ticket (un check `blocking` a, par
  construction, une base à zéro)

### Requirement: Calibrage des tests sur mesure

Toute règle éteinte ou assouplie sur les fichiers de test (`tests/**`, `*.test.ts(x)`, `client/tests/**`)
SHALL être motivée dans la configuration par un commentaire qui cite la mesure ayant justifié
l'extinction, et SHALL ne jamais s'appliquer au code de production.

#### Scenario: Extinction motivée

- **WHEN** une règle est désactivée pour les fichiers de test dans `eslint.config.analyse.js` ou
  `pyproject.toml`
- **THEN** la ligne porte un commentaire avec le nombre de remontées qu'elle éteint et la raison
  (contrat de la bibliothèque de test, patron arrange/act/assert)

#### Scenario: Production intacte

- **WHEN** la même règle est enfreinte dans `client/src/` (hors tests) ou `backend/`
- **THEN** elle est remontée

### Requirement: Sortie lisible par un agent

Le frontend SHALL exposer `npm run check:agent` qui joue la passe d'analyse jusqu'au bout, écrit un
rapport JSON sous `client/reports/analyse/` et imprime un digest (règles les plus remontées, fichiers
les plus touchés), en sortant toujours en succès : il constate, le verdict est celui de la gate.

#### Scenario: Rapport écrit malgré des remontées

- **WHEN** `npm run check:agent` est joué sur une base qui a des remontées
- **THEN** `client/reports/analyse/eslint.json` existe, le digest liste au plus 8 règles et 5
  fichiers, et le code de sortie est 0

#### Scenario: Rapport hors du dépôt suivi

- **WHEN** `npm run check:agent` a écrit ses rapports
- **THEN** `git status --porcelain` ne les liste pas (`client/reports/` est ignoré)

### Requirement: Documentation de la gate

`docs/ci.md` SHALL lister les commandes `analyse`, `check:agent` et `deptry` avec leur intention et
leur coût mesuré, et `runbooks/ci.md` SHALL dire explicitement qu'aucun de ces checks n'est joué par
la CI GitHub — la gate du cycle `run` est leur seul juge.

#### Scenario: Cap à jour pour ticket-briefer

- **WHEN** `ticket-briefer` lit `docs/ci.md` pour un ticket frontend
- **THEN** il y trouve la commande `npm run analyse`, son périmètre (`.ts`/`.tsx` de `src/`) et son
  coût mesuré en secondes

#### Scenario: Frontière CI explicite

- **WHEN** un lecteur cherche dans `runbooks/ci.md` si `frontend-analyse` ou `backend-deps` bloque
  une PR
- **THEN** il lit que ces checks ne sont joués que par la gate du cycle, jamais par `push.yml`
