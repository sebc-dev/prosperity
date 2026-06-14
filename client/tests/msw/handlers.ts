import { http, HttpResponse, type RequestHandler } from 'msw'

import { makeTestJwt } from '../auth'

// Base API du client typé en test (cf. vite.config `test.env.VITE_API_BASE_URL`).
const API = 'http://localhost:8000'

// TokenPair « happy path » : access = JWT de test décodable (exp +15 min), refresh opaque.
function tokenPair() {
  return HttpResponse.json({
    access_token: makeTestJwt({ exp: Math.floor(Date.now() / 1000) + 900 }),
    refresh_token: 'rt-default',
    token_type: 'bearer',
  })
}

// Handlers communs : HAPPY PATHS auth/setup typés depuis le schéma OpenAPI (§5.2), réutilisés par
// les tests de features. Les CAS D'ERREUR (401, 404, réseau) restent ad-hoc via `server.use(...)`.
export const handlers: RequestHandler[] = [
  http.post(`${API}/auth/login`, () => tokenPair()),
  http.post(`${API}/auth/refresh`, () => tokenPair()),
  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
  http.get(`${API}/setup`, () => HttpResponse.json({ status: 'open' })),
  http.post(`${API}/setup`, () => tokenPair()),
]
