# Génération des écrans MVP en maquette + améliorations itératives

Portée : hors-cycle
Ouvert le 2026-09-03 · Actualisé le 2026-09-04 · branche `main` · HEAD `ff06e71`

## Objectif
Couvrir en maquette Claude Design (identité Chêne) le reste des écrans MVP d'E15
au-delà de la boucle financière cœur, et y intégrer au fil de l'eau les améliorations demandées.

## Contexte à charger
à situer    canvas Artifact https://claude.ai/code/artifact/791edba8-0fef-4b88-8643-9b26053838ef — source durable des artboards, ré-extractible via /design (--extract) ; ne pas relire en session
à lire      `docs/ui/README.md` — index des fiches d'écran + procédure de génération (~56 l.)
à lire      `docs/ui/design-system.md` — cadre commun : formatage fr-FR, états, copy, a11y, coque (~167 l.)
à situer    `docs/ui/screens-*.md` — une fiche par écran, lue au coup par coup selon l'écran généré
à situer    `docs/roadmap/E15-ui-mvp.md` — liste complète des écrans MVP
à situer    `client/src/components/layout/app-nav.tsx`, `app-layout.tsx` — vrais composants de coque, cible d'intégration ; pas en phase maquette

## Acquis
- Identité « Chêne » + coque (header + sidebar rétractable rail 72px) *baked* dans chaque artboard.
- Canvas « Prosperity — écrans MVP » : pages Desktop / Tablette / Mobile + Auth. Couvre la boucle financière cœur, le tableau de bord et l'auth.
- Écrans auth faits : 3 publics *nus* (connexion, config 1er admin, acceptation d'invitation), desktop + mobile ; états d'erreur documentés.
- Rendu figé : jamais la couleur seule (toujours doublée d'icône/signe) ; mot de passe ≥ 12 sur setup/invitation.
- Compte › détail + édition des membres faits (desktop/tablette/mobile), rangée 4 Desktop.
- Budgets faits (desktop/tablette/mobile) : liste (consommation, alerte 80 % / dépassement), détail (barre + restant + splits contributeurs « Courses › Frais » + Charger plus) et création (Catégorie picker, Période, Portée, Contributeurs si Commun, report du reliquat). Rangée 5 Desktop.
- Dettes faits (desktop/tablette/mobile) : vue par contrepartie (onglets « On me doit » vert / « Je dois » terre cuite, net orienté, détail libellé court OU « Excédent — {compte/période} », masquage débiteur de la tx source), Régler des dettes (sélection multiple + montant/dette, type interne/externe/compensation, date+note) et Demander un partage (lancé depuis une tx perso : quote-part slider → montant, libellé ≤ 100). Rangée 6 Desktop + annotation `debt-note`.
- Les `.dc.html` de travail vivent dans le scratchpad éphémère → seule source durable = le canvas Artifact.

## Prochaine étape
Générer les écrans MVP restants : catégories, réglages. Prochain : arbre de catégories (`docs/ui/screens-categories.md`) — création/édition/archivage, icône + couleur (pastille).

## Écarté
- Format `specs/NNN` — le dépôt suit `EXX`/roadmap (vision.md §7-9).
- `/design-sync` pour publier les écrans — il importe des composants, pas des maquettes.
- Upload des écrans vers un projet claude.ai/design — aucun chemin dans les outils actuels.
- Export PDF comme support de dev — on référence le HTML source directement.
- Espace insécable des montants — non posée dans la maquette (tout le canvas emploie une espace normale) ; le formatage fr-FR ferme viendra d'`Intl.NumberFormat` à l'intégration React.
