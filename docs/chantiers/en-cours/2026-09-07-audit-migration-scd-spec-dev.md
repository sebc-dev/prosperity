# Suites de l'audit de la migration scd-spec-dev

Portée : socle
Ouvert le 2026-09-07 · Actualisé le 2026-09-07 · branche `chore/migrate-scd-spec-dev` · HEAD `cdfd52e`

## Objectif
Traiter, un lot par session (`/clear` entre chaque), les écarts relevés par l'audit du commit
`a99b4ac`, dans cet ordre — chaque lot a sa vérif, sa branche est notée à l'ouverture :
1. **Tickets + labels** (bloque le 1er `run`) — fait, `cdfd52e`, dans la PR #268.
2. **Socle review** — `docs/architecture.md` (table d'invariants), `docs/ci.md` (cap CI).
3. **Filet CI escape-hatches** — poser une version restreinte au diff, ou documenter le piège du re-jeu de `/setup`.
4. **Dettes doc** — `.planning/` à supprimer, `CONTEXT-MAP.md` vs CLAUDE.md, cycle epic/story absent de CLAUDE.md, « cocher la STORY » dans `config.yaml`.
Lots 2 à 4 : une branche `chore/audit-lot-N` chacun, depuis `main` une fois #268 mergée.

## Contexte à charger
à situer    `openspec/changes/add-dashboard/tickets/` — corrigés au lot 1, ne pas relire
à extraire  `docs/adr/0005-directional-import-graph.md` + `.importlinter` — les invariants de sens de dépendance (lot 2)
à extraire  `docs/Architectures BS.md` › titres de sections — 262 l., ne prendre que les frontières de modules (lot 2)
à extraire  `runbooks/ci.md` › commandes de test par stack — ce que `docs/ci.md` doit résumer (lot 2)
à extraire  `CLAUDE.md` › `### Domain docs` — la promesse `CONTEXT-MAP.md` à corriger (lot 4)
à situer    plugin `scd-spec-dev` 0.2.0 › `commands/setup.md` table d'idempotence — conclusion dans Acquis
à situer    PR #268 — la migration elle-même ; le lot 1 s'y ajoute, ne pas la relire

## Acquis
- Audit joué le 2026-09-07 : schéma scd byte-identique au plugin, `config.yaml` conforme, `validate --strict` vert, 6 cmds + 6 skills OpenSpec complets, zéro résidu `scd-sdd`. Rien à refaire côté montage.
- Lot 1, constaté : les 4 lignes `**Fichiers :**` citent `src/…` alors que le frontend est sous `client/src/` (pas de `src/` racine) ; SC-01a (ticket 01 l.19) dit « plus le placeholder » — l'original disait « ne rend **plus** le placeholder mais le tableau de bord » ; labels `stacked` et `needs-sync` absents sur GitHub alors que pr-author les pose sur toute PR empilée (02/03/04 sont bloqués par 01). La section « Décisions de test » de l'ancien SPEC.md (couture drizzle vs SQLite in-memory, couture composant mock `useQuery`, prior art `queries.test.ts`, `use-account-balance.test.tsx`, `setup-form.test.tsx`, `render.tsx`) n'a pas été migrée : à rapatrier dans `design.md`.
- Lot 1 fait (`cdfd52e`, PR #268) : `client/` préfixé sur les 4 tickets, SC-01a réécrit, « Décisions de test » rapatriées dans `design.md` (§ Decisions), labels `stacked` + `needs-sync` créés sur GitHub.
- Lot 2, constaté : `docs/architecture.md` est lu en dur par review-context/architecture-reviewer ; absent, une violation d'invariant n'est jamais bloquante. `docs/ci.md` est lu en dur par ticket-briefer pour dériver la commande de test ; absent sur un dépôt bi-stack (uv + npm), la commande sera mal dérivée. `docs/caps.md` et `docs/vision.md` ne sont exigés par aucun agent : ne pas les créer.
- Lot 3, constaté : le grep exact du plugin touche 70 fichiers légitimes (`# noqa` documentés) ; l'écarter était juste, l'integrity-reviewer couvre la fonction au review-time. Mais `/setup` re-crée `scd-escape-hatch-guard.yml` à chaque re-jeu.
- Décidé : garder `/opsx:apply` et `openspec-apply-change` (possédés par OpenSpec, reviendraient au `openspec update`) ; laisser `.claude/quality.json` et `review.json` absents (NO-OP documenté, `push.yml` joue déjà lint/typecheck/tests).

## Prochaine étape
Lot 2 : sur `chore/audit-lot-2` créée depuis `main` à jour **une fois #268 mergée**. Écrire
`docs/architecture.md` avec la table des invariants (sens de dépendance depuis ADR-0005 +
`.importlinter`, frontières de modules depuis les titres de `docs/Architectures BS.md`) et un
`docs/ci.md` court qui résume les commandes de test par stack (uv + npm) en pointant `runbooks/ci.md`.
Vérif : les deux fichiers existent ; `docs/architecture.md` contient une table Markdown d'invariants
citant un ADR par ligne ; `docs/ci.md` donne une commande de test exécutable par stack, chacune
jouée et verte.

## Écarté
- Supprimer `/opsx:apply` pour matérialiser l'interdiction — OpenSpec le régénère ; l'interdiction reste comportementale (CLAUDE.md).
- Dupliquer lint/typecheck/tests dans `.claude/quality.json` — double exécution pour un gain nul.
- Poser le filet CI tel que le plugin le génère — rouge permanent sur 70 fichiers brownfield.
- Renommer `runbooks/ci.md` en `docs/ci.md` — `config.yaml` et une fiche archivée le citent ; un `docs/ci.md` court qui pointe dessus suffit.
