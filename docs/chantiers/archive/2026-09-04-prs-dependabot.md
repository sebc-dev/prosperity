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

## Issue
Fermé le 2026-09-04 — toutes les PR Dependabot traitées, **0 restante**.
- **8 PR mergées** (squash, branche supprimée, `main` vérifié à chaque merge), dans l'ordre de risque : #257 tar, #258 postcss, #262 @xmldom/xmldom, #259 undici, #261 js-yaml+@redocly/openapi-core (aucun major, question du fiche tranchée), #260 cryptography 48→50, #265 brace-expansion, #264 browserslist.
- **cryptography 48→50** (seul majeur, runtime backend) jugé sûr car **transitif via PyJWT** (aucun import direct dans le backend) : la résolution `uv` prouve la compatibilité de PyJWT et la CI backend (unit/integration/e2e) est verte sur le rebase — pas d'épluchage du changelog d'une API qu'on n'appelle pas.
- **#263 fermé/superseded par Dependabot** (remplacé par #265, re-scopé au seul 1.1.15→1.1.18) en cours de boucle : « Base branch was modified » à la tentative de merge ; rien mergé par erreur, vérifié sur `main`.
- Méthode tenue : une PR à la fois → `@dependabot rebase` la suivante → CI requise verte **sur base à jour** → merge. `pip-audit` reste nocturne, non exécuté au moment du merge.
