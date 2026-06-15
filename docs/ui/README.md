# UI specs — base de génération des interfaces (E15)

> Documents servant de **base à la génération des écrans** du MVP (E15) par des outils
> **design-to-code** (type v0 / Figma Make…). Ils décrivent le **visuel, l'UX et le contenu
> réel** (champs, états, copy FR, formatage) — **pas** le câblage React/PowerSync (fait à la main
> lors de l'intégration dans `client/`).

## ⚠️ Statut : base provisoire, thème non figé

Le projet **n'a pas encore tranché** son identité visuelle (palette, typo, logo) ni plusieurs
choix d'UX — voir **issue #240** (« Décisions UI/UX à valider »). En conséquence :

- Le `design-system.md` donne des **tokens et patterns par défaut** (baseline shadcn « new-york /
  neutral » posée en S14.2). Ils sont **concrets pour que les outils produisent du cohérent**,
  mais **provisoires** : à remplacer une fois #240 tranchée.
- Les écrans décrivent la **structure, le contenu et les états** (stables, dérivés du domaine),
  pas l'esthétique exacte.

## Comment s'en servir

1. Lire `design-system.md` (tokens, composants, formatage, copy, a11y, états) → c'est le **cadre
   commun** que chaque écran présuppose.
2. Pour générer un écran : prendre sa fiche dans `screens-*.md`, **y joindre `design-system.md`**
   (+ `screen-template.md` si l'outil a besoin de la structure attendue), et demander une maquette.
3. L'intégration réelle (données PowerSync/Drizzle, écritures, API typée, tests) est faite
   **ensuite, à la main** dans le repo — hors de ces documents.

## Sommaire

| Fichier | Contenu |
|---|---|
| `design-system.md` | Tokens (provisoires), composants, couleurs sémantiques, typo, espacement, icônes, responsive + coque applicative, dark mode, **formatage EUR/fr-FR**, conventions de copy FR, accessibilité, états (vide/chargement/erreur/succès), indicateurs offline-first |
| `screen-template.md` | Gabarit d'une fiche-écran (à suivre pour tout nouvel écran) |
| `screens-auth.md` | Connexion, configuration (1er admin), acceptation d'invitation |
| `screens-dashboard.md` | Tableau de bord (solde réel, transactions récentes, dettes, budgets) |
| `screens-accounts.md` | Liste, création (perso/commun), détail, édition des membres |
| `screens-transactions.md` | Liste filtrée, saisie, édition, confirmation/annulation, ligne réutilisable |
| `screens-budgets.md` | Liste (consommation), création, détail |
| `screens-debts.md` | Dettes (par contrepartie), demande de partage, règlement |
| `screens-categories.md` | Arbre de catégories, création/édition/archivage |
| `screens-settings.md` | Profil, foyer (admin), invitations (admin) |

## Périmètre MVP (rappel)

~15 écrans. **Hors MVP** (pas dans ces specs) : solde prévisionnel/projeté, épargne, pointage
bancaire (reconciliation), MCP. Ils arrivent en V1.

## Source de vérité

Le **vocabulaire** et les **règles métier** viennent du glossaire racine `CONTEXT.md` et des ADR
(`docs/adr/`). Les libellés FR déjà codés (badges de synchro, messages d'erreur, formulaires
login/setup) sont **réutilisés tels quels** — voir `design-system.md` §Copy.
