# Prosperity — description générale (contexte)

> **À lire en premier.** Donne le « pourquoi » et le modèle mental de l'application, avant le
> `design-system.md` (le « comment » visuel) et les fiches d'écrans. Source de vérité plus profonde :
> glossaire racine `CONTEXT.md` et spec produit `docs/Sans titre.md`.

## 1. En une phrase

**Prosperity** est une application de **finances personnelles d'un foyer** (plusieurs adultes),
**auto-hébergée**, **offline-first** sur **Web (PWA) et Android**, en **français**. Elle permet la
**saisie manuelle** de transactions, la **gestion partagée de budgets**, et le **suivi des dettes
croisées** entre membres du foyer.

## 2. Philosophie produit (oriente l'UX)

- **Tout est saisissable à la main.** La connexion bancaire est une **commodité, pas une
  dépendance** : l'app doit être pleinement utilisable sans aucune banque connectée.
- **Offline-first.** On saisit hors ligne, l'effet est **immédiat en local**, la synchro est
  **transparente** ensuite (multi-appareils). Jamais de blocage « en attente du serveur ».
- **Confidentialité forte entre membres.** Un **compte personnel** n'est visible que de son
  propriétaire — **même un admin n'y a pas accès**. Les écrans doivent respecter cette étanchéité.
- **Français, ton sobre.** Vocabulaire du glossaire (cf. `design-system.md §9`).

## 3. Utilisateurs cibles

| Persona | Rôle |
|---|---|
| **Adulte 1** | Initie le foyer (1er admin), configure les comptes, invite les autres |
| **Adulte 2** | Saisit ses transactions, accède aux comptes communs ; peut être promu admin |
| *(Futur) Adolescent* | Lecture sur son compte perso — **hors MVP** |

Deux **rôles** : **admin** (gère droits et invitations ; **aucun accès** aux données financières des
comptes dont il n'est pas membre) et **member** (utilisateur ordinaire).

## 4. Modèle mental (concepts clés)

Le **foyer** est l'unité : un déploiement = un foyer, tous ses utilisateurs le partagent.

- **Comptes** — *personnel* (1 propriétaire, isolé) ou *commun* (≥ 2 membres avec **quote-parts**).
  Types : Courant, Livret, Épargne, Espèces, Crédit.
- **Transactions** — un mouvement daté, composé de **splits** dont la somme = **0** (zero-sum). L'UI
  masque cette mécanique (l'utilisateur saisit « j'ai dépensé X chez Y en catégorie Z »). États :
  Brouillon → Planifiée → **Confirmée** (immutable sauf quelques champs) ; Annulée (définitif).
- **Catégories** — un **arbre** partagé par le foyer (couleur + icône) ; les budgets agrègent
  automatiquement les sous-catégories.
- **Budgets** — un montant alloué à une catégorie sur une période (Mensuel/Trimestriel/Annuel),
  *personnel* ou *commun*. On suit la **consommation** ; un **dépassement** sur compte commun peut
  générer une **dette**.
- **Dettes & règlements** — une dette est orientée (qui doit à qui), **dérivée** (lecture seule
  côté client). Deux origines : **excédent budgétaire** sur compte commun, ou **demande de partage**
  explicite sur un compte personnel. On l'apure par un **règlement** (virement interne/externe ou
  compensation comptable), éventuellement multi-dettes.

> Détail exhaustif des règles dans `CONTEXT.md`. Les **invariants** que l'UI doit respecter sont
> repris dans chaque fiche d'écran et dans `design-system.md`.

## 5. Plateformes & contraintes

- **Web PWA** (navigateur) + **Android** (Capacitor). UX **responsive** et **tactile**.
- **Mono-devise EUR** en V1 (pas de sélecteur de devise).
- **Sombre + clair** (bascule manuelle persistée).
- Pas d'inscription publique : on entre dans le foyer par **/setup** (1er admin) ou **invitation**.

## 6. Périmètre — ce que couvrent ces specs (MVP) vs plus tard (V1)

**✅ Dans le MVP** (les écrans de `screens-*.md`) :
connexion / configuration / acceptation d'invitation, tableau de bord (**solde réel**), comptes
(perso + commun), transactions (saisie / édition / confirmation), budgets, dettes & règlements,
catégories, réglages (profil / foyer / invitations).

**🚫 Hors MVP — ne pas générer d'écran pour ça** (arrive en V1) :
- **Agrégation bancaire DSP2** (Enable Banking) et **pointage / réconciliation** bancaire.
- **Soldes prévisionnel et projeté** (le MVP n'affiche **que le solde réel**).
- **Épargne / objectifs** (savings goals).
- **Assistant IA via MCP** (Claude interroge/conseille).
- **2FA / PAT** (step-up) — optionnel, hors écrans MVP.

> Ces fonctionnalités existent dans la vision produit (`docs/Sans titre.md`) mais **ne font pas
> partie** de la première vague d'UI. Un agent générateur doit s'en tenir au périmètre MVP ci-dessus.

## 7. Statut design (rappel)

L'**identité visuelle et plusieurs choix d'UX ne sont pas figés** → issue **#240**. Les specs
donnent des **défauts cohérents et provisoires** ; la **structure, le contenu et les règles métier**
sont stables.
