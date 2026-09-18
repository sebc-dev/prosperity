# 02 — Frontières de zones du client vérifiées par la passe `analyse`, en avis

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `client/eslint.config.analyse.js`, `client/package.json`, `client/package-lock.json`, `client/tests/lint/boundaries.test.ts`

## Ce que ça livre

La passe `npm run analyse` (ticket 01) vérifie le **sens des dépendances** entre les zones de
`client/src/` avec `eslint-plugin-boundaries` et `eslint-import-resolver-typescript` (requis pour
l'alias `@/`). Zones : `app`, `pages`, `features`, `components/business`, `components/ui`, `hooks`,
`lib`. Matrice déclarée : `app → *` ; `pages → features, components/*, hooks, lib` ;
`features → components/*, hooks, lib` ; `components/business → components/ui, hooks, lib` ;
`hooks → lib` ; `components/ui` et `lib` → **rien** (interne à la zone). Un import hors matrice remonte
`boundaries/element-types` avec le fichier source et la zone cible ; un import autorisé est silencieux.

**Sévérité `warn`, pas `error`** : la matrice de zones n'est promue par aucun ADR — `docs/architecture.md`
§ Frontend : « un écart est une suggestion, pas un bloquant ». Une règle `error` créerait un invariant
sans décision. Seule exception connue : l'arête `lib → ui` (`app`, `pages`, `features`, `components`,
`hooks`) est l'invariant A11 de l'ADR 0018 (`docs/adr/0018-client-network-boundary-via-lib.md`) ; elle
est gardée **en bloquant, ailleurs** — par `no-restricted-imports` dans `eslint.config.js` (change
`arch-guards`, fichiers disjoints). Ce ticket ne la promeut pas en `error` dans `boundaries` et ne
retire rien à `eslint.config.js` : c'est un suivi séparé. Aucun code de `src/` n'est déplacé pour
satisfaire la matrice ; ce que la mesure révèle se consigne dans la PR.

**Comment prouver** : même patron que 01 — `lintText` sous vitest avec un `filePath` réel de la zone
visée (ex. `src/lib/powersync/connector.ts` important `@/components/business/...` ; `src/pages/...`
important la même cible) ; assertions filtrées sur `ruleId === 'boundaries/element-types'`, `severity`
(1 = warn) et le message (fichier source, zone cible). Cas limite : l'import via l'alias `@/` est résolu
comme un chemin relatif.

## Critères
- [ ] Un fichier de `src/lib/` qui importe un module de `src/components/business/` fait remonter `boundaries/element-types` avec le fichier source et la zone cible   (SC-02a)
- [ ] Un fichier de `src/pages/` qui importe un module de `src/components/business/` ne fait rien remonter pour cette arête   (SC-02b)
- [ ] Une infraction de frontière est remontée comme **avis** : les règles `boundaries/*` ont la sévérité `warn` et n'échouent pas la commande à elles seules — tant qu'aucun ADR ne promeut la matrice de zones (l'arête `lib → ui` de l'ADR 0018 est gardée à part, en bloquant, par `eslint.config.js`)   (SC-02c)
