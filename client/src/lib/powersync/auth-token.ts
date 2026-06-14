// SOURCE UNIQUE du JWT, SANS dépendance interne → casse le cycle ESM connector↔upload
// (les deux l'importent). Placeholder S14.4 : lecture brute en localStorage ; bascule vers
// `lib/storage` (Secure Storage) en S14.5, refresh sur 401 en S14.6.
const JWT_KEY = 'prosperity-jwt'

export function getToken(): string | null {
  const token = localStorage.getItem(JWT_KEY)
  // Garde-fou : le placeholder localStorage (exposition XSS) ne doit JAMAIS atteindre une
  // release sans Secure Storage. En PROD on avertit (sans jamais logger le token lui-même).
  if (import.meta.env.PROD && token) {
    console.warn(
      '[powersync] JWT en localStorage (placeholder S14.4) — exposition XSS, Secure Storage requis (S14.5)',
    )
  }
  return token
}
