# E15 — UI MVP (~15 écrans)

> **Durée estimée** : 15-20 jours
> **Statut** : not started
> **Dépend de** : E14
> **Bloque** : E16
> **ADRs activés** : aucun (matérialisation UI des décisions existantes)

---

## Objectif

Construire l'UI complète du MVP : layout + nav + login + setup + dashboard (solde réel uniquement, cf. Sans titre.md §6 MVP) + comptes + transactions + budgets + dettes + categories + settings + invitation accept. Pas de soldes prévisionnel/projeté (V1), pas d'épargne (V1), pas de pointage (V1).

Livrable agrégé : un foyer peut utiliser l'app complètement offline-first sur PWA Web et Android. Les 5 parcours E2E Playwright (cf. stratégie de tests §6.2) passent.

---

## Stories

### S15.1 — Layout + navigation + protected routes

| Phase | Description | Diff |
|---|---|---|
| **P15.1.1** | `app/layout.tsx` : header (logo, user menu, theme toggle), nav lateral/bottom selon viewport, footer minimal. Responsive Tailwind | ~200 |
| **P15.1.2** | `app/protected-route.tsx` : guard qui redirige `/login` si pas authentifié, sinon affiche children. Tests | ~80 |
| **P15.1.3** | Routes principales déclarées dans `app/router.tsx` : `/`, `/login`, `/setup`, `/accept-invite`, `/accounts`, `/transactions`, `/budgets`, `/debts`, `/categories`, `/settings`. Tests : navigation fonctionnelle | ~120 |

---

### S15.2 — Pages login + setup + accept-invite

| Phase | Description | Diff |
|---|---|---|
| **P15.2.1** | `pages/login.tsx` + `features/login/` : form email + password, gestion erreurs (mauvais creds, account disabled). Tests MSW | ~150 |
| **P15.2.2** | `pages/setup.tsx` + `features/setup/` : form premier admin (display_name + email + password). Détecte `/setup` 404 → redirige vers `/login`. Tests | ~150 |
| **P15.2.3** | `pages/accept-invite.tsx` + `features/accept-invite/` : extrait token de l'URL, fetch `/accept-invite?token=…` (GET) pour pré-remplir email, soumet display_name + password. Gestion 410. Tests | ~180 |

---

### S15.3 — Dashboard (solde réel MVP)

| Phase | Description | Diff |
|---|---|---|
| **P15.3.1** | `pages/dashboard.tsx` : grille de widgets non configurables en MVP (configurables en V2 cf. spec). Widgets : `BalancePanel` (par compte), `RecentTransactions` (10 dernières), `DebtSummary` (par contrepartie), `BudgetSummary` (top 3 budgets actifs avec % consommé). Hooks Drizzle pour offline-first | ~250 |
| **P15.3.2** | `components/business/BalancePanel.tsx` : solde réel par compte avec icon type + nom + montant formaté français + freshness indicator (cf. ADR 0009 BankingReader, mais V1 simple : "synced X min ago") | ~120 |
| **P15.3.3** | `components/business/DebtSummary.tsx` : par contrepartie, net amount avec indicateur sens. Click → drill-down vers `/debts?with=user_id` | ~120 |

---

### S15.4 — Page accounts

| Phase | Description | Diff |
|---|---|---|
| **P15.4.1** | `pages/accounts.tsx` : liste comptes (personnels + communs où user est membre), filtre type, archivés masqués par défaut. Tests | ~150 |
| **P15.4.2** | `features/create-personal-account/`, `features/create-shared-account/` : forms dédiés avec member picker + ratio slider pour shared. Tests interaction | ~250 |
| **P15.4.3** | `pages/accounts/[id].tsx` : détail compte + liste transactions du compte + bouton "ajouter une transaction". Tests | ~200 |
| **P15.4.4** | `features/edit-account-members/` : modal d'édition des members (ajouter, retirer, changer ratios). Validation client `sum == 1.0` avec re-balance auto. Tests | ~200 |

---

### S15.5 — Pages transactions

| Phase | Description | Diff |
|---|---|---|
| **P15.5.1** | `pages/transactions.tsx` : liste paginée (cursor) avec filtres (compte, date, catégorie, montant, texte). Recherche full-text en V2 — V1 = filtres simples | ~250 |
| **P15.5.2** | `features/add-transaction/` : form de saisie rapide (montant, payee, catégorie, compte source, date), conversion auto en 2 splits zero-sum (split sortant compte + split entrant catégorie pour les dépenses). État initial `planned` (l'utilisateur confirme explicitement). Tests | ~300 |
| **P15.5.3** | `features/edit-transaction-draft/` : édition libre tant que `draft|planned`, édition restreinte si `confirmed` (form qui désactive les champs gelés avec tooltip "champ figé après confirmation"). Tests | ~200 |
| **P15.5.4** | `features/confirm-transaction/`, `features/void-transaction/` : boutons + dialogs de confirmation. Gestion `UncategorizedExpenseError` (toast utilisateur). Tests | ~150 |
| **P15.5.5** | `components/business/TransactionRow.tsx` : ligne réutilisable avec date, payee, catégorie, montant, état badge. Click → modal détail | ~120 |

---

### S15.6 — Page budgets

| Phase | Description | Diff |
|---|---|---|
| **P15.6.1** | `pages/budgets.tsx` : liste budgets actifs (perso + commun où user contributor) avec barre de consommation visuelle. Filtre par scope. Tests | ~200 |
| **P15.6.2** | `features/create-budget/` : form (catégorie picker hiérarchique, montant, période, scope, contributors). Tests | ~250 |
| **P15.6.3** | `pages/budgets/[id].tsx` : détail budget + liste paginée des splits qui contribuent (`GET /budgets/{id}/contributing-splits`). Tests | ~180 |

---

### S15.7 — Pages debts + settlements

| Phase | Description | Diff |
|---|---|---|
| **P15.7.1** | `pages/debts.tsx` : liste dettes du user, agrégée par contrepartie. Onglets "owed to me" / "owed by me". Tests | ~200 |
| **P15.7.2** | `features/create-share-request/` : depuis une transaction perso (édition ou détail), bouton "demander partage". Form : `requested_from` user picker, ratio slider, short_label. Tests | ~250 |
| **P15.7.3** | `features/settle-debts/` : depuis la vue dettes avec une contrepartie, sélection multiple de dettes ouvertes + form Settlement (type, linked_tx_id optionnel, settled_at, note). Tests | ~300 |

---

### S15.8 — Page categories

| Phase | Description | Diff |
|---|---|---|
| **P15.8.1** | `pages/categories.tsx` : vue arborescente avec drag-and-drop pour déplacer (ou simple modal "déplacer vers..."). Indentation visuelle 5 niveaux max, au-delà collapse. Tests | ~250 |
| **P15.8.2** | `features/create-edit-category/`, `features/archive-category/` : forms avec color picker + icon picker. Tests | ~200 |

---

### S15.9 — Settings + invitations

| Phase | Description | Diff |
|---|---|---|
| **P15.9.1** | `pages/settings.tsx` : tabs : Profile, Household (admin only), Invitations (admin only). Tests | ~150 |
| **P15.9.2** | Tab Profile : édition display_name, email (avec re-auth required pour email), changement password (avec re-auth required). Tests | ~200 |
| **P15.9.3** | Tab Invitations (admin only) : liste des invitations pending, bouton "inviter", bouton "régénérer", bouton "révoquer". Tests | ~200 |
| **P15.9.4** | Tab Household : édition `name`, affichage `base_currency` (read-only V1). Audit log accessible en lecture | ~150 |

---

### S15.10 — Playwright E2E (5 parcours MVP)

| Phase | Description | Diff |
|---|---|---|
| **P15.10.1** | Setup Playwright + browser binaries en CI nightly (cf. stratégie de tests §9.3). Première E2E `playwright.config.ts` | ~120 |
| **P15.10.2** | Parcours 1 : Onboarding multi-user (cf. stratégie de tests §6.2 #1). Vérifier flow complet : `/setup` → login → créer compte personnel → créer compte commun → inviter user 2 → accepter → user 2 se logge | ~250 |
| **P15.10.3** | Parcours 2 : Sync offline → online golden path. Saisir 3 tx offline, sync, vérifier sur 2e device | ~200 |
| **P15.10.4** | Parcours 4 : Cycle de dette complet (share_request + settlement multi-line). Pour MVP : pas Enable Banking ni reconciliation. Pas le parcours 3 ni 5 en MVP — ils arrivent en V1 (reconciliation, MCP) | ~280 |
| **P15.10.5** | Parcours MVP-spécifique : import OFX (preview hybride + dedup + categorisation post-import). Spécifique au MVP avant que Enable Banking arrive | ~250 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S15.1 (3 phases) | Layout + nav | 400 | 400 |
| S15.2 (3 phases) | Login + setup + invite | 480 | 880 |
| S15.3 (3 phases) | Dashboard | 490 | 1370 |
| S15.4 (4 phases) | Accounts | 800 | 2170 |
| S15.5 (5 phases) | Transactions | 1020 | 3190 |
| S15.6 (3 phases) | Budgets | 630 | 3820 |
| S15.7 (3 phases) | Debts + settlements | 750 | 4570 |
| S15.8 (2 phases) | Categories | 450 | 5020 |
| S15.9 (4 phases) | Settings | 700 | 5720 |
| S15.10 (5 phases) | Playwright E2E | 1100 | 6820 |
| **Total** | **10 stories / 35 phases** | **~6820 lignes** | |

---

## Critères d'acceptation

- [ ] Les ~15 écrans MVP sont fonctionnels (login, setup, dashboard, 2× accounts, 3× transactions, 2× budgets, 1× debts, 1× categories, 4× settings)
- [ ] L'app fonctionne offline-first : saisir une transaction sans réseau, voir le résultat immédiatement, sync à la reconnexion
- [ ] Sur PWA Web + Android émulé, l'UX est cohérente (responsive, touch-friendly)
- [ ] Les 4 parcours Playwright MVP passent (les parcours 3 = reconciliation, 5 = MCP arrivent en V1)
- [ ] Le freshness indicator affiche "synced X min ago" sur le dashboard
- [ ] Édition d'un champ gelé d'une tx confirmed → toast utilisateur ("ce champ ne peut plus être modifié")
- [ ] CI frontend verte, coverage `components/business/ ≥ 75%`, `features/ ≥ 65%`

---

## Notes pour l'implémenteur

- C'est le plus gros epic en volume (~7000 lignes). À planifier sur 3-4 semaines.
- Les composants `components/business/` sont les plus testés ; les pages sont testées via E2E plutôt que Vitest (test composé d'interactions inter-composants).
- L'ajout drag-and-drop categories (P15.8.1) peut être remplacé par un simple modal "déplacer vers..." en MVP si délai serré. À trancher au moment du dev.
- Les widgets dashboard configurables sont V2 — en MVP, layout fixe.
- Pour les forms complexes (create budget avec category picker hiérarchique, create shared account avec member ratios), utiliser `react-hook-form` + `zod` pour la validation client. Cohérence avec Pydantic côté serveur.
