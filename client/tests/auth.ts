import { tokenStore, type AuthTokens } from '@/lib/auth/token-store'

// base64url SANS padding (comme un vrai segment JWT).
function b64url(o: unknown): string {
  return btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// JWT de test : signature FACTICE (le décodage client n'est pas vérifié — le serveur fait foi).
// `exp` en epoch s ; `aud`/`iss` posés par cohérence avec ADR 0016 (non lus côté client).
export function makeTestJwt({
  sub = '00000000-0000-0000-0000-000000000001',
  exp,
}: {
  sub?: string
  exp: number
}): string {
  const h = b64url({ alg: 'HS256', typ: 'JWT' })
  const p = b64url({ sub, exp, aud: 'prosperity-api', iss: 'prosperity-auth' })
  return `${h}.${p}.sig`
}

// Pré-amorce le token-store (chemin authentifié) sans passer par le réseau — `exp` à +15 min par
// défaut. Utilisé par `renderWithProviders({ auth: 'authenticated' })` et les tests de garde.
export function seedAuth(over: Partial<AuthTokens> = {}) {
  const accessExp = over.accessExp ?? Math.floor(Date.now() / 1000) + 900
  tokenStore.set({
    accessToken: over.accessToken ?? makeTestJwt({ exp: accessExp }),
    refreshToken: over.refreshToken ?? 'rt-test',
    accessExp,
  })
}
