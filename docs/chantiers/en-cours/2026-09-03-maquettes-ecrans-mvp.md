# Génération des écrans MVP en maquette + améliorations itératives

Portée : hors-cycle
Ouvert le 2026-09-03 · Actualisé le 2026-09-04 · branche `main` · HEAD `cd8a38a`

## Objectif
Couvrir en maquette Claude Design (identité Chêne) le reste des écrans MVP d'E15
au-delà de la boucle financière cœur, et y intégrer au fil de l'eau les améliorations demandées.

## Contexte à charger
à situer    canvas Artifact https://claude.ai/code/artifact/791edba8-0fef-4b88-8643-9b26053838ef — source durable des artboards, ré-extractible via /design (--extract) ; ne pas relire en session
à lire      `docs/ui/README.md` — index des fiches d'écran + procédure de génération (~55 l.)
à lire      `docs/ui/design-system.md` — cadre commun : formatage fr-FR, états, copy, a11y, coque (~168 l.)
à situer    `docs/ui/screens-*.md` — une fiche par écran, lue au coup par coup selon l'écran généré
à situer    `docs/roadmap/E15-ui-mvp.md` — liste complète des écrans MVP
à situer    `client/src/components/layout/app-nav.tsx`, `app-layout.tsx` — vrais composants de coque, cible d'intégration ; pas en phase maquette

## Acquis
- Identité « Chêne » + coque (header + sidebar rétractable rail 72px) *baked* dans chaque artboard.
- Canvas « Prosperity — écrans MVP » : pages Desktop / Tablette / Mobile + Auth. Couvre la boucle financière cœur, le tableau de bord et l'auth.
- Écrans auth faits : 3 publics *nus* (connexion, config 1er admin, acceptation d'invitation), desktop + mobile ; états d'erreur documentés.
- Rendu figé : montants en espaces insécables ; jamais la couleur seule ; mot de passe ≥ 12 sur setup/invitation.
- Compte › détail + édition des membres faits (desktop/tablette/mobile), rangée 4 Desktop.
- Les `.dc.html` de travail vivent dans le scratchpad éphémère → seule source durable = le canvas Artifact.

## Prochaine étape
Générer les écrans MVP restants : détail/création de budget, dettes, catégories, réglages. Prochain : détail/création de budget (`docs/ui/screens-budgets.md`).

## Écarté
- Format `specs/NNN` — le dépôt suit `EXX`/roadmap (vision.md §7-9).
- `/design-sync` pour publier les écrans — il importe des composants, pas des maquettes.
- Upload des écrans vers un projet claude.ai/design — aucun chemin dans les outils actuels.
- Export PDF comme support de dev — on référence le HTML source directement.
