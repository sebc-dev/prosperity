# Suites de l'audit de la migration scd-spec-dev

Portée : socle
Ouvert le 2026-09-07 · Actualisé le 2026-09-07 · branche `chore/audit-lot-4` · HEAD `93fd75f`

## Objectif
Traiter, un lot par session (`/clear` entre chaque), les écarts relevés par l'audit du commit
`a99b4ac`, dans cet ordre — chaque lot sur sa branche `chore/audit-lot-N` depuis `main`, sa PR, sa vérif :
1. **Tickets + labels** (bloquait le 1er `run`).
2. **Socle review** — `docs/architecture.md` (table d'invariants), `docs/ci.md` (cap CI).
3. **Filet CI escape-hatches** — le porter par les linters plutôt que par le grep du plugin.
4. **Dettes doc** — `.planning/` à supprimer, `CONTEXT-MAP.md` vs CLAUDE.md, cycle epic/story absent de CLAUDE.md, « cocher la STORY » dans `config.yaml`.

## Contexte à charger
à lire      `docs/agents/domain.md` — ce que CLAUDE.md promet sur le multi-contexte, à confronter au disque (42 l., lot 4)
à lire      `docs/roadmap/README.md` — le cycle epic/story que CLAUDE.md ne décrit pas (81 l., lot 4)
à extraire  `CLAUDE.md` › `### Domain docs` — la promesse `CONTEXT-MAP.md` à corriger (lot 4)
à extraire  `openspec/config.yaml` › `operations.archive` — la guidance « Cocher la STORY » à revoir (lot 4)
à situer    `.planning/` — 7 fichiers hérités, à supprimer au lot 4, ne pas lire

## Acquis
- Audit joué le 2026-09-07 : montage OpenSpec conforme (schéma, config, validate, commandes, zéro résidu `scd-sdd`). Rien à refaire côté montage.
- J'ai décidé de ne pas créer `docs/caps.md` ni `docs/vision.md` : aucun agent ne les exige.
- Lot 4, constaté : `CONTEXT-MAP.md` n'existe pas ; `.planning/` existe encore ; CLAUDE.md ne mentionne ni epic ni story alors que `config.yaml` exige de backréférencer une STORY et de la cocher à l'archive.
- Décidé : garder `/opsx:apply` et `openspec-apply-change` (possédés par OpenSpec, reviendraient au `openspec update`) ; laisser `.claude/review.json` absent.
- Lot 4 fait (PR lot 4) : `.planning/` supprimé ; CLAUDE.md et `docs/agents/domain.md` décrivent le mono-contexte réel ; CLAUDE.md nomme `docs/roadmap/` et le lien change ↳ STORY ; « Cocher la STORY » reformulé en « clore la STORY » (issue + ligne `> **Statut**` de l'epic) car les epics n'ont pas de case par story.
- Vu en passant, non traité : `test_property_one_result_per_mutation_in_order` (`tests/unit/test_sync_dispatcher.py`) a échoué une fois sous `-n auto`, vert seul et au re-jeu — instable, hors périmètre.

## Prochaine étape
Aucune : les quatre lots sont livrés.

## Écarté
- Supprimer `/opsx:apply` pour matérialiser l'interdiction — OpenSpec le régénère ; l'interdiction reste comportementale (CLAUDE.md).
- Dupliquer lint/typecheck/tests dans `.claude/quality.json` — double exécution pour un gain nul.
- Poser le filet CI tel que le plugin le génère — rouge permanent sur >100 lignes brownfield légitimes.
- Job grep restreint au diff de la PR — rouge à chaque `# noqa: <code>` légitime, exceptions à gérer ; ruff PGH004 + RUF100 font le contrôle sans bruit.
- Documenter seulement le piège de `/setup` — laissait un `# noqa` nu ou mort possible sans aucun signal.
- Renommer `runbooks/ci.md` en `docs/ci.md` — `config.yaml` et une fiche archivée le citent ; un `docs/ci.md` court qui pointe dessus suffit.

## Issue
Les quatre lots de l'audit sont livrés, chacun par sa PR depuis `main` : lot 1 (tickets + labels),
lot 2 (`docs/architecture.md`, `docs/ci.md`, PR #269), lot 3 (filet escape-hatches porté par ruff
PGH004 + RUF100, PR #270), lot 4 (dettes doc, branche `chore/audit-lot-4`). Reste hors périmètre le
test instable `test_property_one_result_per_mutation_in_order` sous `-n auto`, noté dans Acquis.
