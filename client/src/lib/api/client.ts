import createClient from 'openapi-fetch'

import type { paths } from './schema'

// Client REST typé de bout en bout : chaque chemin / méthode / réponse est dérivé de `paths`
// (généré depuis l'OpenAPI FastAPI — aucun mapping manuel). `baseUrl` = backend FastAPI
// (`VITE_API_BASE_URL`, variable PUBLIQUE inlinée dans le bundle ; jamais de secret).
//
// LEAF VOLONTAIRE : `createClient` nu, sans middleware. L'injection du Bearer (et plus tard
// le refresh-on-401) est enregistrée par `lib/auth/session.ts` au boot (`api.use(...)`), pour
// que ce module reste un leaf framework-agnostique sans dépendre du token-store.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL as string,
  // `fetch` résolu À CHAQUE APPEL (et non capturé au `createClient`) : openapi-fetch fige
  // sinon `globalThis.fetch` à l'import, AVANT que MSW (FetchInterceptor) ne le remplace au
  // `beforeAll` → les requêtes échapperaient à l'interception réseau des tests. Sans effet en
  // prod (le `fetch` global y est stable).
  fetch: (request: Request) => globalThis.fetch(request),
})
