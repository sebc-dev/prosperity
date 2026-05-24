# E14 — Frontend bootstrap (Capacitor + React + PowerSync client)

> **Durée estimée** : 5-7 jours
> **Statut** : not started
> **Dépend de** : E13
> **Bloque** : E15
> **ADRs activés** : (cohérence ADR 0014 côté client via `WriteResult.error` handling)

---

## Objectif

Scaffolder le client : Capacitor 8 + React 19 + TypeScript + Vite 6 + Drizzle (schéma local) + Tailwind + shadcn/ui + PowerSync Web/Capacitor SDK + Vitest + Testing Library + MSW. Auth client (login + JWT storage) + wrapper SSE + wrapper PowerSync avec gestion `WriteResult.error`.

Livrable agrégé : `npm run dev` démarre Vite, l'app charge, on peut se login, JWT est stocké en `localStorage` (web) ou Capacitor Secure Storage (mobile), PowerSync se connecte au backend, on voit le squelette d'app (layout + nav). `npx cap run android` démarre sur émulateur.

---

## Stories

### S14.1 — Vite + React 19 + TypeScript

| Phase | Description | Diff |
|---|---|---|
| **P14.1.1** | `client/` : init Vite + React 19 + TypeScript strict + ESLint + Prettier config. Tests : `npm run build` passe, `npm run lint` passe, app vide affiche "Hello" | ~150 |
| **P14.1.2** | Router (TanStack Router ou React Router 7) + structure `app/`, `pages/`, `features/`, `components/business/`, `components/ui/`, `lib/`, `hooks/`, `types/`. README expliquant la structure et le mapping vers ADRs | ~120 |

---

### S14.2 — Tailwind + shadcn/ui + theme

| Phase | Description | Diff |
|---|---|---|
| **P14.2.1** | Tailwind 4 setup + Tailwind preflight + Tailwind dark mode. Vérifier build OK | ~80 |
| **P14.2.2** | `npx shadcn init` + premières primitives (Button, Input, Card, Dialog, Toast). Tests visuels manuels | ~100 |
| **P14.2.3** | Theme : couleurs cohérentes (palette à proposer ou laisser le défaut shadcn neutral) + dark mode toggle dans le layout | ~80 |

---

### S14.3 — Drizzle local schema

| Phase | Description | Diff |
|---|---|---|
| **P14.3.1** | `lib/drizzle/` : schema TS qui mirror les tables sync server-side (transactions, splits, accounts, account_members, categories, budgets, debts, settlements, settlement_lines, share_requests, savings_goals, savings_goal_allocations, notifications, users_public). Tests : `drizzle-kit push` génère un schéma SQLite | ~250 |
| **P14.3.2** | Drizzle queries helpers : `useTransactions(filters)`, `useAccountBalance(account_id)`, `useDebtsForCurrentUser()`, etc. Hooks réactifs sur changements PowerSync. Tests Vitest | ~200 |

---

### S14.4 — PowerSync client setup

| Phase | Description | Diff |
|---|---|---|
| **P14.4.1** | `lib/powersync/` : init `PowerSyncDatabase` avec schema Drizzle, connexion au backend (URL + JWT). Tests : `MockPowerSyncDatabase` setup (cf. stratégie de tests §5.3) | ~180 |
| **P14.4.2** | Write upload handler client side : route les mutations Drizzle vers `POST /sync/upload`, gère les `WriteResult.error` typés. Sur `validation_error` ou `immutable_field_violation` → toast utilisateur + purge mutation locale. Sur 500 → laisser PowerSync retry. Tests avec MSW | ~250 |
| **P14.4.3** | Hooks PowerSync : `usePowerSync()`, `useSyncStatus()` (badge "syncing", "synced just now", "offline"). Tests avec `MockPowerSyncDatabase` | ~150 |

---

### S14.5 — Capacitor 8 + Android

| Phase | Description | Diff |
|---|---|---|
| **P14.5.1** | `npx cap add android` + `capacitor.config.ts` (appId, app name, build target). Cohérence avec skill `webapp-to-capacitor` du repo. Tests : `npx cap run android` démarre sur émulateur, l'app charge | ~120 |
| **P14.5.2** | Capacitor Secure Storage plugin pour JWT (à la place de localStorage sur mobile). Wrapper `lib/storage/` qui choisit Secure Storage si Capacitor, localStorage sinon. Tests | ~150 |
| **P14.5.3** | Documentation `runbooks/android_build.md` : prérequis Android Studio, signing config V1 (debug only en MVP, release en E16) | ~80 |

---

### S14.6 — Auth client

| Phase | Description | Diff |
|---|---|---|
| **P14.6.1** | `lib/api/` : client typé OpenAPI généré (via `openapi-typescript` ou `orval`) depuis le schéma FastAPI export. Tests build : génération doit être idempotente | ~120 |
| **P14.6.2** | `hooks/useAuth.ts` : `login(email, password)`, `logout()`, `refresh()`, JWT storage + refresh automatique avant expiration (15min - 1min). Tests avec MSW | ~200 |
| **P14.6.3** | `features/login/` : page de login + form + gestion erreurs. `features/setup/` : page `/setup` pour premier admin (suit la même base UI mais sans flow JWT préalable). Tests interaction | ~250 |

---

### S14.7 — SSE wrapper + Vitest setup

| Phase | Description | Diff |
|---|---|---|
| **P14.7.1** | `lib/sse/` : wrapper `EventSource` qui : (i) appelle `POST /sse/token` pour obtenir le JWT short-lived (cf. ADR 0012), (ii) maintient `Last-Event-ID` localement et le re-passe à la reconnexion, (iii) refresh le JWT toutes les 4 min. Tests MSW couvrant disconnect/reconnect | ~200 |
| **P14.7.2** | Vitest setup : `tests/setup.ts`, MSW handlers communs, helpers fixture. Tests trivial Hello | ~120 |
| **P14.7.3** | CI frontend dans `.github/workflows/push.yml` : ajouter `frontend-lint` (eslint + prettier + tsc), `frontend-unit` (vitest run), `frontend-build` (vite build + capacitor sync). Tests : la CI tourne et passe | ~100 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S14.1 (2 phases) | Vite + React | 270 | 270 |
| S14.2 (3 phases) | Tailwind + shadcn | 260 | 530 |
| S14.3 (2 phases) | Drizzle local | 450 | 980 |
| S14.4 (3 phases) | PowerSync client | 580 | 1560 |
| S14.5 (3 phases) | Capacitor + Android | 350 | 1910 |
| S14.6 (3 phases) | Auth client | 570 | 2480 |
| S14.7 (3 phases) | SSE + Vitest + CI | 420 | 2900 |
| **Total** | **7 stories / 19 phases** | **~2900 lignes** | |

---

## Critères d'acceptation

- [ ] `npm run dev` démarre, l'app charge à `http://localhost:5173`
- [ ] `npm run build` produit un bundle Vite, `npx cap sync android` synchronise
- [ ] `npx cap run android` démarre l'app sur émulateur
- [ ] Login fonctionne (JWT stocké en Secure Storage sur mobile, localStorage sur web)
- [ ] PowerSync se connecte au backend, sync rules respectées (tester avec 2 users distincts)
- [ ] `WriteResult.error: immutable_field_violation` côté serveur déclenche un toast côté client + purge de la mutation locale
- [ ] SSE se connecte, reconnecte après disconnect, refresh le JWT
- [ ] CI frontend verte (lint + unit + build + cap sync)

---

## Notes pour l'implémenteur

- Capacitor 8 est récent (mai 2026). Vérifier que `@capacitor/secure-storage` + `@capacitor/push-notifications` (E19) sont à jour. Sinon stub temporairement.
- Le client typé OpenAPI : pas de manuel mapping des routes/types. Re-générer à chaque push backend (CI job qui fail si désynchro).
- Le wrapper SSE refresh JWT toutes les 4 min même si la connexion est ouverte (le token expire à 5 min — laisser 1 min de marge). Si refresh fail → close SSE et retry login.
- Tailwind 4 (récent) introduit des changements vs Tailwind 3. Vérifier compatibilité shadcn (qui suit la version courante).
- React 19 strict mode active : tester que les effects ne s'exécutent pas en double (React 19 dev mode mount/unmount/remount comportement). Si bugs PowerSync hooks, c'est probablement là.
- Pas de PWA setup en E14 (manifest + service worker) — c'est pour E15 ou E16.
