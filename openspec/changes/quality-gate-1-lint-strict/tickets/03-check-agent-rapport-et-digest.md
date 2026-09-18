# 03 — `check:agent` : la passe d'analyse jouée jusqu'au bout, rapport JSON et digest

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `client/scripts/rapports-analyse.mjs`, `client/package.json`, `.gitignore`, `client/tests/lint/rapports-analyse.test.ts`

## Ce que ça livre

Depuis `client/`, `npm run check:agent` joue la passe `analyse` (ticket 01) **jusqu'au bout** — une
chaîne `&&` s'arrête au premier rouge et un agent n'aurait qu'un tiers du tableau — via un script
`client/scripts/rapports-analyse.mjs` : ESLint en `--format json --output-file reports/analyse/eslint.json`,
puis un **digest** imprimé sur la sortie standard (les règles les plus remontées, **au plus 8** ; les
fichiers les plus touchés, **au plus 5** ; le total). Le script **sort toujours en 0** : il constate, le
verdict est celui de la gate. `client/reports/` est ignoré par git (entrée dans le `.gitignore` racine,
section « Frontend (client/) », comme `client/coverage/`).

**Comment prouver** : un test par critère, `SC-03x` dans le nom. Le digest est une fonction pure
(JSON ESLint → règles/fichiers classés, tronqués) : l'exporter du script et la tester sur un JSON
synthétique avec plus de 8 règles et 5 fichiers. Le contrat de commande (fichier écrit, code 0) se
prouve en jouant le script (`spawnSync('node', ['scripts/rapports-analyse.mjs'])`) — sur un `src/` qui
peut être vert : le script écrit le rapport et sort en 0 dans les deux cas. `git status --porcelain
client/reports` vide après exécution.

## Critères
- [ ] Joué sur une base qui a des remontées, `npm run check:agent` laisse `client/reports/analyse/eslint.json` sur disque, imprime un digest d'au plus 8 règles et 5 fichiers, et sort avec le code 0   (SC-03a)
- [ ] Après `npm run check:agent`, `git status --porcelain` ne liste aucun fichier de `client/reports/` (répertoire ignoré)   (SC-03b)
