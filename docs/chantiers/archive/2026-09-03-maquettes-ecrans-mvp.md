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
- Dettes faits (desktop/tablette/mobile) : vue par contrepartie dans les DEUX sens — « Je dois » (débiteur, terre cuite, signe −, bouton « Régler avec ») et « On me doit » (créancier, vert crédit, signe +, rangées informationnelles sans bouton) ; détail libellé court OU « Excédent — {compte/période} », masquage débiteur de la tx source. Plus Régler des dettes (sélection multiple + montant/dette, type interne/externe/compensation-sans-flux, date+note ; feuille sur mobile) et Demander un partage (lancé depuis une tx perso : quote-part slider → montant, libellé ≤ 100). Page « Dettes » + annotation `debt-note`.
- **Canvas réorganisé par ÉCRAN D'APPLICATION** (2026-09-04) : une `page` par écran (Tableau de bord · Comptes · Transactions · Budgets · Dettes · Auth), et dans chaque page une RANGÉE par sous-écran groupant ses formats côte à côte. Remplace l'ancien découpage par format (pages Desktop/Tablette/Mobile) — les mentions « Rangée N Desktop » des acquis précédents sont caduques. Notes de domaine repositionnées sur leur page.
- **4 formats par écran** (2026-09-04) : colonnes Desktop 1280×832 (x=0) · Tablette PAYSAGE 1194×834 (x=1360) · Tablette PORTRAIT 834×1194 (x=2634) · Mobile 390×844 (x=3548) ; pitch de rangée 1314. Auth = Desktop + Tablette paysage + Mobile (pas de portrait ; mobile x=2634 ; pitch 964). Le paysage est dérivé du desktop (cadre → 1194×834, la coque md est conservée). **Convention à suivre pour tout nouvel écran : les 4 formats, groupés en rangée sur la page de l'écran.**
- **Zone principale en crème uniforme** (2026-09-04) : la carte de contenu englobante (classe `.card`) passe du blanc au crème `--bg #f6f2eb` sur les 53 artboards concernés → la zone principale lit crème partout, comme derrière les modales. Le token `--card #ffffff` est INCHANGÉ (boutons, inputs, modales gardent leur blanc/contraste) ; header/sidebar restent `--surface`. Auth (carte centrée focale) et feuilles plein écran mobile (déjà crème) non touchés. **Convention à suivre : `.card` en crème pour tout nouvel écran.**
- Catégories faites (page « Catégories », 4 formats × 3 sous-écrans = 12 artboards) : arbre (pastille couleur+icône, indentation + connecteur, menu ⋯ Modifier/Déplacer/Archiver, case « Afficher les archivées », prévention des cycles évoquée en note), Créer/éditer (Nom · Parent · Couleur picker+swatches+hex · Icône picker), Archiver (dialogue de confirmation léger, soft-delete sans cascade). Annotation `categorie-note`.
- Les `.dc.html` de travail vivent dans le scratchpad éphémère → seule source durable = le canvas Artifact.

## Prochaine étape
Générer le dernier écran MVP : **nouvelle page « Réglages »** (`docs/ui/screens-settings.md`) — Profil, Foyer (admin), Invitations (admin) —, aux 4 formats groupés en rangée, cartes crème, « Réglages » actif dans la nav.

## Écarté
- Format `specs/NNN` — le dépôt suit `EXX`/roadmap (vision.md §7-9).
- `/design-sync` pour publier les écrans — il importe des composants, pas des maquettes.
- Upload des écrans vers un projet claude.ai/design — aucun chemin dans les outils actuels.
- Export PDF comme support de dev — on référence le HTML source directement.
- Espace insécable des montants — non posée dans la maquette (tout le canvas emploie une espace normale) ; le formatage fr-FR ferme viendra d'`Intl.NumberFormat` à l'intégration React.

## Issue
Fermé le 2026-09-04 — **objectif atteint** : tous les écrans MVP d'E15 sont maquettés (identité Chêne).
- **Dernier écran livré (cette session)** : page « Réglages » (Profil · Foyer admin · Invitations admin · dialogue Inviter), 4 rangées × 4 formats = 16 artboards ; conventions respectées (4 formats groupés, `.card` crème, « Réglages » actif dans la nav, « Plus » sur mobile).
- Relecture de fond intégrée : copy exacte « L'ancien lien ne fonctionnera plus. », casse du rôle harmonisée (« member »), « expire dans N j » complété sur mobile, cibles tactiles ≥ 44 px.
- Améliorations « au fil de l'eau » — 5 corrections sur Catégories : menu ⋯ ouvert (Modifier · Déplacer vers… · Archiver), état archivé grisé + Désarchiver, copy mobile « Afficher les catégories archivées », variante « Modifier la catégorie », prévention des cycles (sélecteur Parent ouvert, descendants désactivés).
- **Source durable** : canvas Artifact « Prosperity — écrans MVP » — 101 artboards, 8 pages — https://claude.ai/code/artifact/791edba8-0fef-4b88-8643-9b26053838ef. Ré-extractible via `/design` (`--extract`) ; les `.dc.html` de travail restent éphémères (scratchpad).
- **Aucun commit repo** : travail 100 % maquette, hors code. L'intégration réelle (React/PowerSync, données typées, tests) reste à faire, séparément, écran par écran.
