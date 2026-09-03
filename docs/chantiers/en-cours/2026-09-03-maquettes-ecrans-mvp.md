# Génération des écrans MVP en maquette + améliorations itératives

Portée : hors-cycle
Ouvert le 2026-09-03 · Actualisé le 2026-09-03 · branche `main` · HEAD `8d45906`

## Objectif
Couvrir en maquette Claude Design (identité Chêne) le reste des écrans MVP d'E15
au-delà de la boucle financière cœur, et y intégrer au fil de l'eau les améliorations
demandées.

## Contexte à charger
à situer    canvas Artifact https://claude.ai/code/artifact/791edba8-0fef-4b88-8643-9b26053838ef — source durable des artboards, ré-extractible via /design (--extract) ; ne pas relire en session
à extraire  `client/src/index.css` › `:root` (tokens Chêne) — palette/typo de référence, seul ce bloc compte (~230 l.)
à lire      `client/src/components/layout/nav-items.ts` — 7 sections + PRIMARY_NAV_COUNT, base nav/sidebar (~40 l.)
à situer    `client/src/components/layout/app-nav.tsx`, `app-layout.tsx` — vrais composants de coque, cible finale du rétractable ; pas en phase maquette
à lire      `docs/ui/README.md` — index des fiches d'écran restantes (~55 l.)
à situer    `docs/roadmap/E15-ui-mvp.md` — liste complète des écrans MVP à couvrir

## Acquis
- Identité « Chêne » reprise telle quelle du vrai `index.css` (teal/sable/terre cuite ; Fraunces/Nunito Sans/JetBrains Mono) — #240 est de fait tranché dans le code, pas « provisoire ».
- Maquettes en canvas `.dc.html`, pas en `specs/NNN` (le dépôt suit roadmap EXX). Import futur prévu dans `docs/ui/specs/<écran>/` (pattern `tableau_bord`).
- Responsive figé : breakpoint md 768px, sidebar ≥ 768, barre basse 5 + « Plus » < 768 ; tablette = reflow de la coque desktop.
- Les `.dc.html` de travail vivent dans le scratchpad éphémère → la seule source durable est le canvas Artifact.
- Sidebar rétractable faite dans la maquette : toggle « Replier » en bas de sidebar (arbitré — pas dans le header), rail 72px à icônes + tooltip au survol, chevron qui pivote. Déclinée sur les 12 artboards desktop+tablette (logique DCLogic + tweak `collapsed`) ; mobiles inchangés (barre basse).

## Prochaine étape
Générer les écrans MVP restants avec cette coque rétractable — auth (login/setup/invitation), dashboard, détail/édition de compte, détail/création de budget, dettes, catégories, réglages — d'après l'index `docs/ui/README.md`. Commencer par le dashboard (porte d'entrée).

## Écarté
- Format `specs/NNN` — le dépôt suit `EXX`/roadmap (vision.md §7-9).
- `/design-sync` pour publier les écrans — il importe des composants, pas des maquettes.
- Upload des écrans vers un projet claude.ai/design — aucun chemin dans les outils actuels.
- Export PDF comme support de dev — on référence le HTML source directement.
