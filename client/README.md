# Prosperity — client

Client web/mobile de Prosperity : **Vite 6 + React 19 + TypeScript strict**, packagé
plus tard en app Capacitor (S14.5). Bundle **statique** (servi en `file://` sur
mobile) — pas de SSR.

## Démarrage

```bash
npm install
npm run dev      # Vite sur http://localhost:5173
npm run build    # tsc --noEmit && vite build
npm run lint     # eslint . && prettier --check .
npm run test     # vitest run (harness Vitest + Testing Library + MSW)
```

Node ≥ 22 (cf. `.nvmrc`).

## Routeur — TanStack Router (file-based)

Choix **TanStack Router** (vs React Router 7) :

- Le client est un **bundle statique Capacitor** (`file://`) : aucun SSR/loader
  serveur — le mode « framework » de RR7 (loaders/actions/SSR) est inapplicable.
- **Type-safety bout-en-bout** des routes **et** des `search params` typés (utile
  pour les filtres, ex. `useTransactions(filters)`, S14.3).
- Écosystème commun avec TanStack Query (candidat S14.3).

File-based : les routes vivent dans `src/pages/` (`routesDirectory`), le plugin
`@tanstack/router-plugin/vite` génère `src/routeTree.gen.ts` (committé, ignoré du
lint/format).

## Structure & mapping ADR

Les dossiers anticipent les stories suivantes ; chacun est rattaché à l'ADR/story
qui le peuplera.

| Dossier                | Rôle                                                            | ADR / story              |
| ---------------------- | --------------------------------------------------------------- | ------------------------ |
| `app/`                 | composition racine (providers, `RouterProvider`)                | —                        |
| `pages/`               | routes TanStack (`routesDirectory`)                             | —                        |
| `lib/drizzle/`         | schéma local miroir des tables sync                             | ADR 0003 — S14.3         |
| `lib/powersync/`       | init SDK PowerSync + write upload handler (`WriteResult.error`) | ADR 0014 — S14.4         |
| `lib/api/`             | client REST typé OpenAPI                                        | ADR 0016 — S14.6         |
| `lib/sse/`             | wrapper `EventSource` (token court-lived, resume)               | ADR 0012 — S14.7         |
| `lib/storage/`         | JWT Secure Storage (mobile) / localStorage (web)                | S14.5                    |
| `features/`            | parcours métier (confirmable, MCP confirm…)                     | ADR 0017 / 0004 — S14.6+ |
| `components/business/` | composants métier **testés** (Vitest, §5.1)                     | Stratégie §5.1 — S14.2+  |
| `components/ui/`       | primitives shadcn/ui (non testées en propre)                    | S14.2                    |
| `hooks/`               | hooks transverses (`useAuth`…)                                  | S14.6                    |
| `types/`               | types partagés                                                  | —                        |

## Sécurité (rappels)

- **Pas de secret dans le bundle** : toute variable `VITE_*` est **inlinée en clair**
  dans le build. N'y mettre que des valeurs publiques ; les variables attendues sont
  documentées dans `.env.example` (les fichiers `.env*` réels sont git-ignorés, sauf
  le gabarit).
- **Pas de `dangerouslySetInnerHTML`** sans sanitisation explicite.
