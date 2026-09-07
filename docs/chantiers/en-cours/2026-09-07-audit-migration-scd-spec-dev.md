# Suites de l'audit de la migration scd-spec-dev

Portée : socle
Ouvert le 2026-09-07 · Actualisé le 2026-09-07 · branche `chore/audit-lot-2` · HEAD `062c4f4`

## Objectif
Traiter, un lot par session (`/clear` entre chaque), les écarts relevés par l'audit du commit
`a99b4ac`, dans cet ordre — chaque lot sur sa branche `chore/audit-lot-N` depuis `main`, sa PR, sa vérif :
1. **Tickets + labels** (bloquait le 1er `run`).
2. **Socle review** — `docs/architecture.md` (table d'invariants), `docs/ci.md` (cap CI).
3. **Filet CI escape-hatches** — poser une version restreinte au diff, ou documenter le piège du re-jeu de `/setup`.
4. **Dettes doc** — `.planning/` à supprimer, `CONTEXT-MAP.md` vs CLAUDE.md, cycle epic/story absent de CLAUDE.md, « cocher la STORY » dans `config.yaml`.

## Contexte à charger
à extraire  plugin `scd-spec-dev` 0.2.0 › `commands/setup.md` › `scd-escape-hatch-guard` — le grep que `/setup` génère, à restreindre au diff (lot 3)
à extraire  `.github/workflows/push.yml` › job `ci-required` (L253) — où un job de filet doit se brancher pour bloquer (lot 3)
à lire      `docs/agents/domain.md` — ce que CLAUDE.md promet sur le multi-contexte (42 l., lot 4)
à extraire  `CLAUDE.md` › `### Domain docs` — la promesse `CONTEXT-MAP.md` à corriger (lot 4)
à extraire  `openspec/config.yaml` › « Cocher la STORY » — la règle d'archive à revoir (lot 4)
à situer    `.planning/` — à supprimer au lot 4, ne pas lire

## Acquis
- Audit joué le 2026-09-07 : montage OpenSpec conforme (schéma, config, validate, commandes, zéro résidu `scd-sdd`). Rien à refaire côté montage.
- J'ai décidé de ne pas créer `docs/caps.md` ni `docs/vision.md` : aucun agent ne les exige.
- Lot 2 : le graphe matérialisé par `.importlinter` a 8 modules, pas les 12 d'`Architectures BS.md` ; j'ai fait porter la table sur le réel et renvoyé les modules à venir dans une section à part. Le frontend n'a aucun ADR : repères non contraignants seulement.
- Lot 3, constaté : le grep exact du plugin touche 70 fichiers légitimes (`# noqa` documentés) ; l'écarter était juste, l'integrity-reviewer couvre la fonction au review-time. Mais `/setup` re-crée `scd-escape-hatch-guard.yml` à chaque re-jeu.
- Lot 4, constaté : `CONTEXT-MAP.md` n'existe pas ; `.planning/` existe encore.
- Décidé : garder `/opsx:apply` et `openspec-apply-change` (possédés par OpenSpec, reviendraient au `openspec update`) ; laisser `.claude/review.json` absent.
- Vu en passant, non traité : `test_property_one_result_per_mutation_in_order` (`tests/unit/test_sync_dispatcher.py`) a échoué une fois sous `-n auto`, vert seul et au re-jeu — instable, hors périmètre.

## Prochaine étape
Lot 3 : sur `chore/audit-lot-3` depuis `main` **une fois #269 mergée**. Trancher entre (a) un job CI
qui joue le grep du plugin sur le seul diff de la PR (`git diff --name-only origin/main...HEAD`, en
excluant les `# noqa` documentés), branché sur `ci-required` ; et (b) ne rien poser, et documenter dans
`runbooks/ci.md` que `/setup` re-crée `scd-escape-hatch-guard.yml`, à supprimer après chaque re-jeu.
Vérif (a) : le job passe sur `main` et échoue sur une PR d'essai qui ajoute un `# type: ignore` ;
(b) : le paragraphe existe et `scd-escape-hatch-guard.yml` est absent de `.github/workflows/`.

## Écarté
- Supprimer `/opsx:apply` pour matérialiser l'interdiction — OpenSpec le régénère ; l'interdiction reste comportementale (CLAUDE.md).
- Dupliquer lint/typecheck/tests dans `.claude/quality.json` — double exécution pour un gain nul.
- Poser le filet CI tel que le plugin le génère — rouge permanent sur 70 fichiers brownfield.
- Renommer `runbooks/ci.md` en `docs/ci.md` — `config.yaml` et une fiche archivée le citent ; un `docs/ci.md` court qui pointe dessus suffit.
