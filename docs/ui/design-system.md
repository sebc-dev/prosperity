# Design system — cadre commun des écrans (provisoire, cf. #240)

Cadre que **chaque fiche-écran présuppose**. Les valeurs esthétiques (couleurs, typo) sont des
**défauts** (baseline shadcn « new-york / neutral », S14.2) — **à valider/remplacer via #240**.
Le reste (composants, états, formatage, copy, a11y) est **stable**.

## 1. Tokens (provisoires — #240)

- **Base** : shadcn/ui style « new-york », palette « neutral ». Mode **clair + sombre** (bascule
  manuelle, persistée). Le sombre n'est pas un simple inversement : utiliser les tokens sémantiques.
- **Tokens sémantiques** (noms shadcn, valeurs à fixer en #240) : `background` / `foreground`,
  `card` / `card-foreground`, `popover`, `primary`, `secondary`, `muted` / `muted-foreground`,
  `accent`, `destructive`, `border`, `input`, `ring`. **Ne jamais coder une couleur en dur** : un
  écran doit rester re-thémable en changeant ces tokens.
- **Rayon** : `--radius` (coins arrondis cohérents cartes/boutons/inputs).

### Couleurs **sémantiques métier** (à mapper sur les tokens, pas en dur)

| Usage | Sémantique | Indice visuel (en plus de la couleur) |
|---|---|---|
| Positif / à jour / crédit | succès | icône ✓, vert |
| Avertissement (budget ≥ 80 %) | attention | jaune/ambre, icône alerte |
| Dépassement (budget > 100 %) / on doit | danger | `destructive`, icône |
| Solde / montant neutre | `foreground` | — |
| Hors ligne / inactif | `muted-foreground` | icône wifi barré |

> Accessibilité : **ne jamais** s'appuyer sur la couleur seule (daltonisme) → toujours doubler
> d'une icône, d'un libellé ou d'un signe (+/−).

## 2. Typographie & espacement

- Échelle simple : titre de page (h1), titres de section (h2/h3), corps, légende (texte fin).
- **Tabulaire pour les montants** : les nombres alignés à droite, chiffres à chasse fixe si
  possible (lisibilité des colonnes de montants).
- Espacement : grille de 4 px (p-1=4, p-2=8, p-4=16…). Cartes et sections aérées (padding 16).
- Largeur de contenu : confortable sur desktop (la nav occupe une sidebar 256 px ; cf. §6).

## 3. Composants disponibles (shadcn) et à venir

**Déjà dans le repo** : `Button` (variants : default/ghost/outline/destructive ; sizes : sm/icon),
`Card` (Header/Title/Description/Content), `Input`, `Dialog`, `DropdownMenu`, `Sonner` (toasts).

**À ajouter au besoin par les écrans** (primitives shadcn standard) : `Select`, `Tabs`,
`Checkbox`, `Switch`, `Textarea`, `Label`, `Badge`, `Tooltip`, `Table`, `Slider` (quote-parts),
`Skeleton` (chargement), `Popover`, `Command` (recherche/picker).

**Composants métier réutilisables** (à concevoir, partagés entre écrans) :
- `MoneyAmount` — affiche un montant (cf. §5), couleur sémantique optionnelle (+/−).
- `StateBadge` — badge d'état de transaction (cf. §4).
- `SyncStatusBadge` — **existe** (état de synchro).
- `AccountTypeIcon` / `CategoryChip` (pastille couleur + icône + nom).
- `TransactionRow`, `BalancePanel`, `DebtSummary`, `BudgetSummary` (cf. dashboard).
- `EmptyState`, `ErrorState`, `ConfirmDialog` (cf. §8).

## 4. Badges d'état (transactions) — libellés FR à définir ici

Aucun libellé FR n'est encore codé pour les états. **Convention proposée** (à valider) :

| `state` | Libellé badge | Couleur sémantique |
|---|---|---|
| `draft` | **Brouillon** | `muted` (gris) |
| `planned` | **Planifiée** | `secondary` (bleu doux) |
| `confirmed` | **Confirmée** | succès (vert) |
| `void` | **Annulée** | `muted` barré / `destructive` discret |

## 5. Formatage (fr-FR) — **règle ferme**

Les montants sont stockés en **centimes** (`amount_cents`, entier signé). Il n'existe **pas encore**
d'utilitaire ; tout écran doit afficher via :

```
new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(cents / 100)
// 123456  → "1 234,56 €"   (espace insécable, virgule décimale, € après)
// -5000   → "-50,00 €"
```

- **Signe** : montant qu'on doit / sortie = `−` + couleur danger ; reçu / entrée = `+` + succès.
- **Dates** : `Intl.DateTimeFormat('fr-FR')` → `15/06/2026` ; dates relatives courtes acceptables
  (« il y a 2 min ») pour la fraîcheur de synchro (« synchronisé il y a X min »).
- **Devise** : EUR uniquement en V1 (le foyer est mono-devise) — ne pas exposer de sélecteur.
- **Quote-parts** : afficher en **pourcentage** (`0.5000` → « 50 % ») ; saisie via slider + champ %.

## 6. Responsive & coque applicative (AppLayout — existe)

Toutes les routes **authentifiées** sont rendues dans cette coque (les écrans publics —
login/setup/accept-invite — sont **nus**, centrés, sans nav) :

```
┌──────────────────────────────────────────────────────────┐
│ HEADER : [Logo « Prosperity »]      [SyncBadge][🌓][▼User] │  ← border-b
├───────────┬──────────────────────────────────────────────┤
│ SIDEBAR   │                                              │
│ (≥768px)  │   <contenu de l'écran>                       │
│ 7 entrées │                                              │
│ verticale │                                              │
├───────────┴──────────────────────────────────────────────┤
│ FOOTER : « Prosperity — gestion de budget familial »      │
└──────────────────────────────────────────────────────────┘
< 768px : sidebar masquée → BARRE BASSE FIXE (icônes+labels). ⚠️ 7 items = dense (#240).
```

- **Breakpoint** unique : `md` (768 px). Sidebar `≥ md`, barre basse `< md`.
- Menu user (dropdown) : nom affiché → **Réglages**, **Se déconnecter**.
- Contenu mobile : prévoir `padding-bottom` pour ne pas être masqué par la barre basse fixe.
- Cibles tactiles ≥ 44 px ; listes/cartes confortables au pouce.

## 7. Accessibilité (ferme)

- Cible **WCAG 2.1 AA** : contraste suffisant en clair **et** sombre.
- Chaque contrôle a un **label** (visible ou `aria-label`) ; icônes décoratives `aria-hidden`.
- Navigation **clavier** complète (focus visible `ring`, ordre logique, Échap ferme dialogs/menus).
- États dynamiques annoncés : badge de synchro `role="status"` ; erreurs de formulaire
  `role="alert"` reliées au champ (`aria-describedby`).
- Lien actif de nav : `aria-current="page"`.

## 8. États d'un écran (toujours les 4)

Toute vue affichant des données doit prévoir :

1. **Chargement** : `Skeleton` (silhouettes de cartes/lignes), pas de spinner plein écran.
2. **Vide** : `EmptyState` — icône + phrase + **action primaire** (ex. « Aucun compte. [Créer un
   compte] »). Ton encourageant, jamais culpabilisant.
3. **Erreur** : `ErrorState` (lecture) ou **toast** (action) — message FR générique (cf. §9), bouton
   « Réessayer » si pertinent. Jamais de détail serveur brut.
4. **Peuplé** : la vue normale.

### Offline-first (UX transverse)

- Les **écritures sont optimistes** : l'effet est visible localement **immédiatement** (même hors
  ligne). Pas de spinner bloquant sur « enregistrer ».
- Le **badge de synchro** (header) reflète l'état global : `Hors ligne` / `Synchronisation…` / `À jour`.
- Si le serveur **refuse** une mutation (validation, champ gelé…) : **toast d'erreur FR** + la
  mutation locale est **purgée** (l'UI revient à l'état serveur). Pas de retry en UI (PowerSync gère).

## 9. Copy FR — conventions & réutilisations

- **Langue** : français. Ton **neutre/impersonnel** (formes passives : « Identifiants invalides. »),
  cohérent avec l'existant — pas de « vous » systématique. Phrases courtes, points terminaux.
- **Erreurs génériques** (anti-fuite) : ne jamais afficher le détail serveur. Réutiliser la map
  **exacte** déjà codée (`lib/powersync/error-messages.ts`) :

  | code | message |
  |---|---|
  | `auth_denied` | Action non autorisée. |
  | `validation_error` | Données invalides. |
  | `immutable_field_violation` | Ce champ ne peut pas être modifié. |
  | `uncategorized_expense` | Cette dépense doit être catégorisée. |
  | `unbalanced_transaction` | La transaction n'est pas équilibrée. |
  | `invalid_state_transition` | Ce changement d'état n'est pas autorisé. |
  | `not_found` | Élément introuvable. |
  | *(fallback)* | Une erreur est survenue. |

- **Libellés réutilisés** : badges synchro « Hors ligne / Synchronisation… / À jour » ; login
  « Connexion / Email / Mot de passe / Se connecter / Identifiants invalides. » ; setup
  « Nom du foyer / Nom affiché / Créer le premier administrateur ».
- **Vocabulaire** : utiliser les termes du glossaire `CONTEXT.md` (Foyer, Compte, Transaction,
  Dépense, Split/jambe, Budget, Catégorie, Dette, Demande de partage, Règlement, Quote-part).
  **Éviter** : famille/ménage (→ Foyer), part/ratio (→ quote-part), ligne/poste (→ split).

## 10. Iconographie

- Bibliothèque : **lucide-react** (déjà installée). Style fin, cohérent.
- Repères nav (provisoire, #240) : Tableau de bord `LayoutDashboard`, Comptes `Wallet`,
  Transactions `ArrowLeftRight`, Budgets `PiggyBank`, Dettes `HandCoins`, Catégories `Tags`,
  Réglages `Settings`. Synchro : `WifiOff` / `RefreshCw` (animé) / `Check`.
- Les catégories portent une **icône choisie par l'utilisateur** (champ `icon`) + une **couleur**
  (`#RRGGBB`) → pastille.
