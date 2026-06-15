import { fetchEventSource } from '@microsoft/fetch-event-source'

import { api } from '@/lib/api/client'
import { refresh } from '@/lib/auth/session'

import type { SseClient, SseClientOptions, SseEvent, SseState } from './types'

// Wrapper SSE (ADR 0012). Le navigateur ne pouvant ni poser de header sur `EventSource` natif ni
// l'intercepter via MSW, on utilise `@microsoft/fetch-event-source` (transport `fetch`). Auth :
// `POST /sse/token` (Bearer auto-injecté par le middleware de `lib/auth/session`) → JWT court-lived
// passé en QUERY à `GET /sse/stream?token=…` ; le `Last-Event-ID` est ré-émis en header à chaque
// (ré)ouverture pour le resume.
//
// CYCLE DE VIE POSSÉDÉ (cf. plan §3) : `onerror` THROW systématiquement → on tue le retry interne
// de la lib (qui sinon rejouerait la même URL avec un token périmé) ; une boucle `while`
// séquentielle ré-ouvre. Un SEUL `fetchEventSource` est actif à la fois → aucune connexion
// concurrente. La rotation proactive du token = simple `abort()` ; la lib résout alors la promesse
// (via le listener du `signal`), et la boucle ré-acquiert un token. Idem pour la fermeture
// silencieuse du `200` à l'expiration côté serveur (EOF propre → `resolve` → re-boucle).
//
// SÉCURITÉ : on ne logge JAMAIS l'URL du stream ni le token (l'URL contient `?token=…`). Aucun
// `console.*` ici — symétrie avec le verrou backend `test_sse_no_url_logging`.

// Refresh auth KO → escalade login (pas de retry). Propagée hors de la boucle.
class AuthLost extends Error {}
// Émission du token en échec transitoire (5xx, pas un 401) → backoff, PAS de déconnexion.
class TokenIssueFailed extends Error {}
// 401 à l'ouverture du stream (token SSE périmé) → réémettre un token et rouvrir.
class ReopenWithNewToken extends Error {}
// Réponse HTTP non exploitable. `status === 429` (plafond connexions) → backoff ; sinon → fermeture.
class FatalHttp extends Error {
  constructor(readonly status: number) {
    super(`SSE open failed: ${status}`)
  }
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const backoff = (attempt: number, max: number) => Math.min(max, 500 * 2 ** attempt)

function safeJson(raw: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) as unknown }
  } catch {
    return { ok: false }
  }
}

export function createSseClient(opts: SseClientOptions = {}): SseClient {
  const baseUrl = opts.baseUrl ?? (import.meta.env.VITE_API_BASE_URL as string)
  const margin = (opts.tokenTtlMarginSeconds ?? 60) * 1000
  const maxBackoff = opts.maxBackoffMs ?? 30_000
  const minHealthy = opts.minHealthyMs ?? 1000
  const openWhenHidden = opts.openWhenHidden ?? false

  let started = false
  let stopped = false
  let rotating = false // abort déclenché par le rotateTimer (rotation saine), pas par une coupure
  let openedAt = 0 // horodatage de la dernière ouverture réussie (anti-spin)
  let abort: AbortController | null = null
  let rotateTimer: ReturnType<typeof setTimeout> | undefined
  let lastEventId: string | null = null

  let state: SseState = 'idle'
  const stateListeners = new Set<(s: SseState) => void>()
  const resyncListeners = new Set<() => void>()
  const subs = new Map<string, Set<(e: SseEvent) => void>>()

  function setState(next: SseState) {
    if (next === state) return
    state = next
    stateListeners.forEach((l) => {
      l(next)
    })
  }
  function dispatch(e: SseEvent) {
    subs.get(e.event)?.forEach((h) => {
      h(e)
    })
  }

  // Émet un token. 401 = problème d'auth → UN refresh (single-flight) + UN retry, sinon escalade
  // (`AuthLost`). Un échec NON-401 (5xx) est transitoire → `TokenIssueFailed` (backoff, pas de
  // déconnexion). Un rejet réseau de `api.POST` remonte tel quel (traité aussi en backoff).
  async function issueToken(): Promise<{ token: string; expiresIn: number }> {
    const first = await api.POST('/sse/token')
    if (first.data) return { token: first.data.token, expiresIn: first.data.expires_in }
    if (first.response.status !== 401) throw new TokenIssueFailed()
    if (await refresh()) {
      const retry = await api.POST('/sse/token')
      if (retry.data) return { token: retry.data.token, expiresIn: retry.data.expires_in }
    }
    throw new AuthLost()
  }

  async function run(): Promise<void> {
    let attempt = 0
    while (!stopped) {
      let issued: { token: string; expiresIn: number }
      try {
        issued = await issueToken()
      } catch (e) {
        if (e instanceof AuthLost) {
          setState('unauthenticated')
          return
        }
        // Erreur réseau à l'émission du token → backoff borné, puis retry.
        setState('reconnecting')
        await sleep(backoff(attempt++, maxBackoff))
        continue
      }
      if (stopped) return

      // Rotation proactive : à `expiresIn - marge`, on abort → la boucle ré-acquiert un token.
      // Le flag `rotating` distingue cet abort sain d'une vraie coupure (pas de flash `reconnecting`).
      clearTimeout(rotateTimer)
      rotating = false
      rotateTimer = setTimeout(
        () => {
          rotating = true
          abort?.abort()
        },
        Math.max(0, issued.expiresIn * 1000 - margin),
      )
      abort = new AbortController()
      setState('connecting')

      try {
        await fetchEventSource(`${baseUrl}/sse/stream?token=${encodeURIComponent(issued.token)}`, {
          signal: abort.signal,
          credentials: 'omit', // jamais de cookie cross-origin : auth = token query (ADR 0012)
          openWhenHidden,
          // Header absent à la 1re connexion ; ré-émis après le 1er event reçu (resume).
          headers: lastEventId ? { 'last-event-id': lastEventId } : {},
          onopen: (res) => {
            if (res.status === 401) throw new ReopenWithNewToken()
            if (!res.ok || !res.headers.get('content-type')?.includes('text/event-stream')) {
              throw new FatalHttp(res.status)
            }
            attempt = 0 // reset du backoff sur ouverture réussie
            openedAt = Date.now()
            setState('open')
            return Promise.resolve()
          },
          onmessage: (m) => {
            if (m.id) lastEventId = m.id // une frame sans id (resync) n'avance pas le curseur
            if (m.event === 'resync') {
              resyncListeners.forEach((h) => {
                h()
              })
              return
            }
            const parsed = safeJson(m.data)
            if (!parsed.ok) return // JSON invalide → ignoré (pas de throw, pas de log)
            dispatch({ id: m.id || null, event: m.event, data: parsed.value })
          },
          // THROW toujours → la lib rejette (pas de retry interne) ; on possède la reconnexion.
          onerror: (err) => {
            throw err instanceof Error ? err : new Error('sse stream error')
          },
        })
        // Résolu sans erreur : EOF propre (expiration serveur / overflow) OU abort de rotation/stop.
        if (stopped) return
        if (rotating) {
          rotating = false // rotation saine : reconnexion immédiate, pas de flash `reconnecting`
          continue
        }
        setState('reconnecting')
        // EOF subi : anti-spin si la connexion a duré trop peu (open→EOF immédiat répété).
        if (Date.now() - openedAt < minHealthy) await sleep(backoff(attempt++, maxBackoff))
      } catch (err) {
        if (stopped) return
        if (err instanceof ReopenWithNewToken) continue // 401 ouverture → réémission immédiate
        if (err instanceof FatalHttp && err.status !== 429) {
          setState('closed') // réponse fatale (non-429, non-stream) → arrêt
          return
        }
        // 429 (plafond) ou coupure réseau → backoff borné, puis retry.
        setState('reconnecting')
        await sleep(backoff(attempt++, maxBackoff))
      }
    }
  }

  return {
    start() {
      if (started || stopped) return
      started = true
      void run()
    },
    stop() {
      stopped = true
      clearTimeout(rotateTimer)
      abort?.abort()
      setState('closed')
    },
    getState: () => state,
    subscribe(eventType, handler) {
      let set = subs.get(eventType)
      if (!set) {
        set = new Set()
        subs.set(eventType, set)
      }
      set.add(handler)
      return () => set.delete(handler)
    },
    onResync(handler) {
      resyncListeners.add(handler)
      return () => resyncListeners.delete(handler)
    },
    onStateChange(handler) {
      stateListeners.add(handler)
      return () => stateListeners.delete(handler)
    },
  }
}
