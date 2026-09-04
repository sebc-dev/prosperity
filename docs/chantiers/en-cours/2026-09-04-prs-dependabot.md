# Traitement des PR Dependabot une par une

Portée : hors-cycle
Ouvert le 2026-09-04 · branche `main` · HEAD `8a055ab`

## Objectif
Merger proprement les PR Dependabot ouvertes, une par une, sans orpheliner ni valider
sur des CI périmées, en gardant la lib sensible (cryptography, runtime backend) pour la
fin sous contrôle renforcé.

## Contexte à charger
à lire   `docs/ci.md` — les contrôles bloquants (`ci-required`) qui doivent être verts pour merger (90 l.)
à situer `CLAUDE.md` (gotcha deps) — pip-audit nocturne seulement ; conclusion déjà dans Acquis, ne pas relire
à situer état/CI des PR — se re-dérive à la reprise par `gh pr list` / `gh pr checks <n>`, jamais figé ici

## Acquis
- Décidé : traiter **une PR à la fois** — merger, puis `@dependabot rebase` la suivante,
  attendre la CI verte, merger ; jamais les 6 d'un coup (leurs CI seraient périmées entre elles).
- Ordre de risque arrêté : d'abord les **dev-deps du client** (faible enjeu), patch → minor —
  #257, #258, #262, #259, #261 (vérifier si #261 embarque un major) ; **#260 cryptography en
  dernier** — saut **majeur** (48→50) sur une dep **runtime backend** finance/auth : changelog
  lu + tests backend joués avant merge.
- Constaté : la classe « OK » du `status` = sûreté de **topologie** (base `main`, ni empilé
  ni orphelin), **pas** sûreté du bump — d'où l'instruction PR par PR.
- `pip-audit` ne tourne que la nuit → une PR de dep n'est **pas auditée sécurité au moment du
  merge** (raison de la vigilance sur cryptography).

## Prochaine étape
Instruire **#257** (paquet `tar`, dev-dep client, le plus sûr) : vérifier ses contrôles CI
requis + le bump, décider le merge, puis rebaser la suivante.

## Écarté
- Merge groupé / à l'aveugle des 6 — rejeté : CI périmées entre elles + bump non vérifié.
- Se fier à « OK » du status comme feu vert de merge — c'est une classe de topologie, pas de contenu.
