// SOURCE UNIQUE du JWT en mémoire. Leaf VOLONTAIRE (aucune dépendance interne) : lisible
// SYNCHRONIQUEMENT par les consommateurs hors-React (`powersync/auth-token.ts` → connector/upload),
// et observable par React via `subscribe()` / `useSyncExternalStore`. La PERSISTANCE (`lib/storage`)
// et l'ORCHESTRATION (login/refresh/hydrate) vivent au-dessus (`lib/auth/session.ts`) — ce module
// ne fait que DÉTENIR le pair courant et notifier ses abonnés.

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  accessExp: number // claim `exp` (epoch s), décodé du JWT — planifie le refresh préemptif
}

let current: AuthTokens | null = null
const listeners = new Set<() => void>()

// Méthodes en propriétés-fléchées (et non shorthand) : aucune n'utilise `this` (état module-level),
// et `subscribe`/`get` sont passées NON liées à `useSyncExternalStore` → évite `unbound-method`.
export const tokenStore = {
  get: (): AuthTokens | null => current,
  getAccessToken: (): string | null => current?.accessToken ?? null,
  set: (tokens: AuthTokens | null): void => {
    current = tokens
    listeners.forEach((l) => l())
  },
  subscribe: (l: () => void): (() => void) => {
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  },
}

// Décode le payload JWT (base64url, NON vérifié — le serveur fait foi). Tolère un token
// malformé → null. La normalisation base64url (-_ → +/) + padding est INCLUSE : un `sub` UUID
// encodé peut produire des `-` / `_` que `atob` (base64 strict) rejetterait.
function decodePayload(jwt: string): Record<string, unknown> | null {
  try {
    const part = jwt.split('.')[1]
    if (!part) return null
    const b64 = part
      .replace(/-/g, '+')
      .replace(/_/g, '/')
      .padEnd(Math.ceil(part.length / 4) * 4, '=')
    return JSON.parse(atob(b64)) as Record<string, unknown>
  } catch {
    return null
  }
}

export function decodeExp(jwt: string): number | null {
  const p = decodePayload(jwt)
  return typeof p?.exp === 'number' ? p.exp : null
}

export function decodeSub(jwt: string): string | null {
  const p = decodePayload(jwt)
  return typeof p?.sub === 'string' ? p.sub : null
}
