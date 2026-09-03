# Génération des écrans MVP en maquette + améliorations itératives

Portée : hors-cycle
Ouvert le 2026-09-03 · Actualisé le 2026-09-03 · branche `main` · HEAD `5fb0099`

## Objectif
Couvrir en maquette Claude Design (identité Chêne) le reste des écrans MVP d'E15
au-delà de la boucle financière cœur, et y intégrer au fil de l'eau les améliorations demandées.

## Contexte à charger
à situer    canvas Artifact https://claude.ai/code/artifact/791edba8-0fef-4b88-8643-9b26053838ef — source durable des artboards (coque + composants), ré-extractible via /design (--extract) ; ne pas relire en session
à lire      `docs/ui/README.md` — index des fiches d'écran + procédure de génération (~55 l.)
à lire      `docs/ui/design-system.md` — cadre commun présupposé par chaque écran : formatage fr-FR, états, copy, a11y, coque (~168 l.)
à situer    `docs/ui/screens-*.md` — une fiche par écran, lue au coup par coup selon l'écran généré
à situer    `docs/roadmap/E15-ui-mvp.md` — liste complète des écrans MVP
à situer    `client/src/components/layout/app-nav.tsx`, `app-layout.tsx` — vrais composants de coque, cible d'intégration ; pas en phase maquette

## Acquis
- Identité « Chêne » et coque (header + sidebar rétractable rail 72px) reprises du vrai code et *baked* dans chaque artboard — plus besoin de relire `index.css`/`nav-items.ts`, tout est dans le canvas.
- Canvas renommé « Prosperity — écrans MVP » : 7 écrans (boucle financière + tableau de bord), 3 pages Desktop/Tablette/Mobile, 21 artboards.
- Tableau de bord fait : grille 2×2 des 4 widgets (Soldes / Dettes / Budgets / Transactions récentes), placé en porte d'entrée de chaque page.
- Reflow figé : mobile empile Soldes→Budgets→Dettes→Transactions et condense (2-3 lignes/widget + « Tout voir ») ; tablette garde 2×2 dès md (768) ; desktop grille pleine hauteur.
- Rendu confirmé : montants en espaces insécables (milliers + avant €) ; alerte budget doublée d'une icône/libellé (jamais la couleur seule).
- Les `.dc.html` de travail vivent dans le scratchpad éphémère → seule source durable = le canvas Artifact.

## Prochaine étape
Générer les écrans MVP restants : auth (login / setup 1er admin / acceptation d'invitation — écrans nus, sans coque), puis détail/édition de compte, détail/création de budget, dettes, catégories, réglages. Prochain : auth.

## Écarté
- Format `specs/NNN` — le dépôt suit `EXX`/roadmap (vision.md §7-9).
- `/design-sync` pour publier les écrans — il importe des composants, pas des maquettes.
- Upload des écrans vers un projet claude.ai/design — aucun chemin dans les outils actuels.
- Export PDF comme support de dev — on référence le HTML source directement.
