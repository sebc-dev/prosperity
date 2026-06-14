import { api } from '@/lib/api/client'
import { storage } from '@/lib/storage'
import { STORAGE_KEYS } from '@/lib/storage/types'

import { decodeExp, tokenStore, type AuthTokens } from './token-store'

// ORCHESTRATION de la session (couche `lib`, framework-agnostique) : login / logout / refresh,
// persistance via `lib/storage`, planification du refresh préemptif, et enregistrement du
// middleware Bearer sur le client `api`. `hooks/useAuth.ts` n'est qu'un mince adaptateur React
// par-dessus (`useSyncExternalStore`). Vivre ici (et non dans `hooks/`) permet à
// `lib/powersync/connector.ts` d'appeler `refresh()` sans qu'une couche `lib` importe `hooks/`.

let refreshTimer: ReturnType<typeof setTimeout> | undefined
let refreshInFlight: Promise<boolean> | null = null

// Middleware Bearer (déplacé hors de `client.ts` pour le garder leaf nu) : injecte le token
// mémoire sur CHAQUE appel `api.*`, UNIQUEMENT en header (jamais URL/query). Enregistré une fois
// à l'import de ce module (tiré au boot par AuthProvider → middleware armé avant tout appel).
// login/refresh/setup/logout ne portent pas de token utile : inoffensif (le backend ignore
// l'Authorization sur ces routes publiques).
api.use({
  onRequest({ request }) {
    const token = tokenStore.getAccessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
})

function fromPair(p: { access_token: string; refresh_token: string }): AuthTokens {
  return {
    accessToken: p.access_token,
    refreshToken: p.refresh_token,
    accessExp: decodeExp(p.access_token) ?? 0,
  }
}

// Persiste (async : Secure Storage natif / localStorage web) + place en mémoire + (re)planifie
// le refresh préemptif.
async function commit(tokens: AuthTokens) {
  await Promise.all([
    storage.set(STORAGE_KEYS.jwt, tokens.accessToken),
    storage.set(STORAGE_KEYS.refreshToken, tokens.refreshToken),
  ])
  tokenStore.set(tokens)
  scheduleRefresh(tokens.accessExp)
}

function scheduleRefresh(exp: number) {
  clearTimeout(refreshTimer)
  const ms = Math.max(0, exp * 1000 - Date.now() - 60_000) // exp − 60 s ; jamais négatif
  refreshTimer = setTimeout(() => void refresh(), ms)
}

export async function purge() {
  clearTimeout(refreshTimer)
  refreshTimer = undefined
  await Promise.all([storage.remove(STORAGE_KEYS.jwt), storage.remove(STORAGE_KEYS.refreshToken)])
  tokenStore.set(null)
}

// SINGLE-FLIGHT : N appels simultanés (timer préemptif + `fetchCredentials` réactif + futurs
// 401) partagent UNE seule requête `/auth/refresh` → pas de stampede ni de rotation concurrente
// du refresh token (qui invaliderait la famille côté serveur). Renvoie `true` si la session est
// vivante après l'appel, `false` si elle a été purgée (refresh impossible/refusé).
export function refresh(): Promise<boolean> {
  refreshInFlight ??= doRefresh().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

async function doRefresh(): Promise<boolean> {
  const rt = tokenStore.get()?.refreshToken
  if (!rt) {
    await purge()
    return false
  }
  const { data, error } = await api.POST('/auth/refresh', { body: { refresh_token: rt } })
  if (error || !data) {
    await purge() // 401 (inconnu/expiré/révoqué) → session morte → logout local
    return false
  }
  await commit(fromPair(data))
  return true
}

export async function login(email: string, password: string) {
  const { data, error } = await api.POST('/auth/login', { body: { email, password } })
  if (error || !data) throw new Error('invalid_credentials') // 401 → message FR par l'appelant
  await commit(fromPair(data))
}

export async function logout() {
  const rt = tokenStore.get()?.refreshToken
  if (rt) await api.POST('/auth/logout', { body: { refresh_token: rt } }) // 204 idempotent
  await purge()
}

// Auto-login du 1er admin (`POST /setup` renvoie un TokenPair) — consommé par `features/setup`.
export { commit as commitTokens }

// Hydratation au boot (appelée par AuthProvider AVANT le montage du routeur). Repeuple le
// token-store depuis le storage, puis refresh immédiat si l'access est expiré/proche, sinon
// planifie le refresh préemptif.
export async function hydrateSession() {
  const [access, rt] = await Promise.all([
    storage.get(STORAGE_KEYS.jwt),
    storage.get(STORAGE_KEYS.refreshToken),
  ])
  if (!access || !rt) return
  const exp = decodeExp(access) ?? 0
  tokenStore.set({ accessToken: access, refreshToken: rt, accessExp: exp })
  if (exp * 1000 - Date.now() < 60_000)
    await refresh() // expiré/proche → refresh immédiat
  else scheduleRefresh(exp)
}
