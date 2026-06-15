// @vitest-environment jsdom
// `@microsoft/fetch-event-source` requiert `document`/`window` (visibilitychange, timers) → jsdom
// obligatoire (pas d'env `node`). MSW 2 stream un vrai `ReadableStream` lu incrémentalement.
import { http, HttpResponse } from 'msw'
import { afterEach, expect, test, vi } from 'vitest'

import { makeTestJwt, seedAuth } from '@tests/auth'
import { server } from '@tests/msw/server'
import { frame, heartbeat, resync, sseChannel, sseStream } from '@tests/msw/sse'

import { createSseClient } from './client'
import type { SseClient, SseEvent } from './types'

const API = 'http://localhost:8000'

// Accès indexé sûr (tsconfig `noUncheckedIndexedAccess`) : lève si l'index est hors bornes.
function at<T>(arr: readonly T[], i: number): T {
  const v = arr[i]
  if (v === undefined) throw new Error(`index ${i} hors bornes`)
  return v
}

let active: SseClient | null = null
afterEach(() => {
  active?.stop()
  active = null
  vi.useRealTimers()
})

// ---- Handlers ad-hoc (reset en afterEach global) -------------------------------------------

type TokenSpec = number | { token: string; expires_in?: number }
function onToken(seq: TokenSpec[]) {
  const calls: { auth: string | null }[] = []
  let i = 0
  server.use(
    http.post(`${API}/sse/token`, ({ request }) => {
      calls.push({ auth: request.headers.get('authorization') })
      const spec = at(seq, Math.min(i, seq.length - 1))
      i += 1
      if (typeof spec === 'number') return new HttpResponse(null, { status: spec })
      return HttpResponse.json({ token: spec.token, expires_in: spec.expires_in ?? 300 })
    }),
  )
  return calls
}

interface StreamCall {
  token: string | null
  lastEventId: string | null
  auth: string | null
}
function onStream(make: (call: number) => Response) {
  const calls: StreamCall[] = []
  server.use(
    http.get(`${API}/sse/stream`, ({ request }) => {
      const url = new URL(request.url)
      calls.push({
        token: url.searchParams.get('token'),
        lastEventId: request.headers.get('last-event-id'),
        auth: request.headers.get('authorization'),
      })
      return make(calls.length)
    }),
  )
  return calls
}

// Poll réel (cas immédiats, sans timer applicatif).
async function until(pred: () => boolean, timeout = 1500) {
  const start = Date.now()
  while (!pred()) {
    if (Date.now() - start > timeout) throw new Error('until: timeout')
    await new Promise((r) => setTimeout(r, 5))
  }
}
// Poll sous fake timers : avance le temps par pas en flushant les microtasks (réseau/stream).
async function fakeUntil(pred: () => boolean, maxMs = 5000) {
  let elapsed = 0
  while (!pred()) {
    await vi.advanceTimersByTimeAsync(10)
    elapsed += 10
    if (elapsed > maxMs) throw new Error('fakeUntil: timeout')
  }
}

// ---- 1. Happy path -------------------------------------------------------------------------

test('token_then_stream_happy_path', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const ch = sseChannel()
  onStream(() => ch.response)
  const got: SseEvent[] = []
  active = createSseClient()
  active.subscribe('notification', (e) => got.push(e))
  active.start()
  await until(() => active!.getState() === 'open')
  ch.push(frame(1, 'notification', { x: 1 }))
  await until(() => got.length === 1)
  expect(got[0]).toEqual({ id: '1', event: 'notification', data: { x: 1 } })
  expect(active.getState()).toBe('open')
})

// ---- 2. Bearer sur POST /sse/token ---------------------------------------------------------

test('token_request_carries_bearer', async () => {
  seedAuth()
  const tokenCalls = onToken([{ token: 't1' }])
  onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => tokenCalls.length === 1)
  expect(at(tokenCalls, 0).auth).toMatch(/^Bearer /)
})

// ---- 3. Token en query, pas de Bearer sur le stream ----------------------------------------

test('stream_url_carries_query_token', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const streamCalls = onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => streamCalls.length === 1)
  expect(at(streamCalls, 0).token).toBe('t1')
  expect(at(streamCalls, 0).auth).toBeNull()
})

// ---- 4. Heartbeat ignoré -------------------------------------------------------------------

test('heartbeat_is_ignored', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const ch = sseChannel()
  onStream(() => ch.response)
  const got: SseEvent[] = []
  active = createSseClient()
  active.subscribe('notification', (e) => got.push(e))
  active.start()
  await until(() => active!.getState() === 'open')
  ch.push(heartbeat)
  ch.push(frame(1, 'notification', { ok: true }))
  await until(() => got.length === 1)
  expect(got).toHaveLength(1)
  expect(active.getState()).toBe('open')
})

// ---- 5. Resync routé vers onResync, sans avancer l'id --------------------------------------

test('resync_routes_to_callback_and_does_not_advance_id', async () => {
  seedAuth()
  onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? sseStream([frame(7, 'notification', {}), resync]) : sseChannel().response
  })
  const resyncs: number[] = []
  active = createSseClient()
  active.onResync(() => resyncs.push(1))
  active.start()
  await until(() => streamCalls.length === 2)
  expect(resyncs).toHaveLength(1)
  // L'id n'a été avancé que par la frame 7, pas par le resync (sans id) → resume sur 7.
  expect(at(streamCalls, 1).lastEventId).toBe('7')
})

// ---- 6. Reconnexion : ré-émet Last-Event-ID -----------------------------------------------

test('reconnect_resends_last_event_id_header', async () => {
  seedAuth()
  onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? sseStream([frame(5, 'notification', {})]) : sseChannel().response
  })
  active = createSseClient()
  active.start()
  await until(() => streamCalls.length === 2)
  expect(at(streamCalls, 1).lastEventId).toBe('5')
})

// ---- 7. Rotation proactive du token avant expiration --------------------------------------

test('token_rotation_before_expiry', async () => {
  vi.useFakeTimers()
  seedAuth()
  const tokenCalls = onToken([
    { token: 't1', expires_in: 100 },
    { token: 't2', expires_in: 100 },
  ])
  const streamCalls = onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await fakeUntil(() => active!.getState() === 'open')
  expect(streamCalls).toHaveLength(1)
  // Rotation à (100 - 60) = 40 s : abort → la boucle ré-acquiert un token et rouvre.
  await vi.advanceTimersByTimeAsync(40_000)
  await fakeUntil(() => streamCalls.length === 2)
  expect(tokenCalls).toHaveLength(2)
  expect(at(streamCalls, 1).token).toBe('t2')
})

// ---- 8. Échec du refresh → escalade login --------------------------------------------------

test('token_refresh_failure_escalates', async () => {
  seedAuth()
  onToken([401])
  server.use(http.post(`${API}/auth/refresh`, () => new HttpResponse(null, { status: 401 })))
  const streamCalls = onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => active!.getState() === 'unauthenticated')
  expect(streamCalls).toHaveLength(0)
})

// ---- 9. 401 à l'ouverture → réémission du token --------------------------------------------

test('stream_401_triggers_token_reissue', async () => {
  seedAuth()
  const tokenCalls = onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? new HttpResponse(null, { status: 401 }) : sseChannel().response
  })
  active = createSseClient()
  active.start()
  await until(() => active!.getState() === 'open')
  expect(tokenCalls.length).toBeGreaterThanOrEqual(2)
  expect(at(streamCalls, 1).token).toBe('t2')
})

// ---- 10. 429 (plafond) → backoff borné -----------------------------------------------------

test('too_many_connections_backs_off', async () => {
  vi.useFakeTimers()
  seedAuth()
  onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? new HttpResponse(null, { status: 429 }) : sseChannel().response
  })
  active = createSseClient({ maxBackoffMs: 50 })
  active.start()
  await fakeUntil(() => active!.getState() === 'reconnecting')
  expect(streamCalls).toHaveLength(1) // pas de spin : pas encore reconnecté
  await vi.advanceTimersByTimeAsync(50)
  await fakeUntil(() => active!.getState() === 'open')
  expect(streamCalls).toHaveLength(2)
})

// ---- 11. stop() : abort + purge des timers -------------------------------------------------

test('stop_aborts_and_clears_timers', async () => {
  seedAuth()
  const tokenCalls = onToken([{ token: 't1' }])
  onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => active!.getState() === 'open')
  const before = tokenCalls.length
  active.stop()
  expect(active.getState()).toBe('closed')
  await new Promise((r) => setTimeout(r, 30))
  expect(tokenCalls.length).toBe(before) // aucun nouvel appel après stop
})

// ---- 12. data non-JSON ignorée sans crash --------------------------------------------------

test('malformed_event_data_does_not_crash', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const ch = sseChannel()
  onStream(() => ch.response)
  const got: SseEvent[] = []
  active = createSseClient()
  active.subscribe('notification', (e) => got.push(e))
  active.start()
  await until(() => active!.getState() === 'open')
  ch.push('id: 1\nevent: notification\ndata: {bad json\n\n')
  ch.push(frame(2, 'notification', { ok: true }))
  await until(() => got.length === 1)
  expect(at(got, 0).data).toEqual({ ok: true }) // la frame valide passe, la malformée est ignorée
  expect(active.getState()).toBe('open')
})

// ---- 13. 1re connexion : pas de Last-Event-ID (dual du cas 6) ------------------------------

test('first_connect_omits_last_event_id_header', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const streamCalls = onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => streamCalls.length === 1)
  expect(at(streamCalls, 0).lastEventId).toBeNull()
})

// ---- 14. onStateChange : séquence de transitions ------------------------------------------

test('state_transitions_are_emitted', async () => {
  seedAuth()
  onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? sseStream([]) : sseChannel().response // EOF immédiat → reconnexion
  })
  const states: string[] = []
  active = createSseClient()
  active.onStateChange((s) => states.push(s))
  active.start()
  await until(() => streamCalls.length === 2 && active!.getState() === 'open')
  expect(states.slice(0, 3)).toEqual(['connecting', 'open', 'reconnecting'])
  expect(states[states.length - 1]).toBe('open')
})

// ---- 15. Smoke transport : parsing incrémental multi-frames -------------------------------

test('transport_parses_progressive_multiframe', async () => {
  seedAuth()
  onToken([{ token: 't1' }])
  const ch = sseChannel()
  onStream(() => ch.response)
  const got: SseEvent[] = []
  active = createSseClient()
  active.subscribe('notification', (e) => got.push(e))
  active.start()
  await until(() => active!.getState() === 'open')
  ch.push(frame(1, 'notification', { n: 1 }))
  await until(() => got.length === 1) // livré AVANT la 2e frame → parsing incrémental, pas buffer
  ch.push(frame(2, 'notification', { n: 2 }))
  await until(() => got.length === 2)
  expect(got.map((e) => e.id)).toEqual(['1', '2'])
})

// ---- 16. Reset du backoff après reconnexion réussie ---------------------------------------

test('backoff_resets_after_successful_reopen', async () => {
  vi.useFakeTimers()
  seedAuth()
  onToken([{ token: 't1' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    // 429×3 (délais 500→1000→2000) → call4 ouvre+EOF (reset) → call5 429 (délai 500) → call6 ouvre.
    if (call <= 3 || call === 5) return new HttpResponse(null, { status: 429 })
    if (call === 4) return sseStream([]) // ouvre (reset attempt) puis EOF → reconnexion immédiate
    return sseChannel().response
  })
  active = createSseClient({ maxBackoffMs: 10_000 })
  active.start()

  // 3× 429 : les délais croissent 500 → 1000 → 2000 (backoff exponentiel).
  await fakeUntil(() => streamCalls.length === 1)
  await vi.advanceTimersByTimeAsync(500)
  await fakeUntil(() => streamCalls.length === 2)
  await vi.advanceTimersByTimeAsync(1000)
  await fakeUntil(() => streamCalls.length === 3)
  // Pré-reset : le délai avant la 4e tentative est LONG (2000ms) → 600ms ne suffit pas.
  await vi.advanceTimersByTimeAsync(600)
  expect(streamCalls).toHaveLength(3)
  // Laisse expirer les 2000ms → call 4 ouvre (reset attempt=0) puis EOF → reconnexion immédiate → call 5 (429).
  await vi.advanceTimersByTimeAsync(1400)
  await fakeUntil(() => streamCalls.length === 5)
  // Post-reset : le backoff est repassé à 500ms → 700ms suffit (preuve du reset : sinon ce serait 4000).
  await vi.advanceTimersByTimeAsync(700)
  await fakeUntil(() => streamCalls.length === 6)
  expect(streamCalls.length).toBe(6)
})

// ---- 17. Fermeture silencieuse à l'expiration → nouveau token ------------------------------

test('silent_expiry_close_reissues_token', async () => {
  seedAuth()
  const tokenCalls = onToken([{ token: 't1' }, { token: 't2' }])
  let call = 0
  const streamCalls = onStream(() => {
    call += 1
    return call === 1 ? sseStream([]) : sseChannel().response // EOF propre (sans 401)
  })
  active = createSseClient()
  active.start()
  await until(() => streamCalls.length === 2)
  expect(tokenCalls).toHaveLength(2) // un nouveau POST /sse/token après la fermeture
  expect(at(streamCalls, 1).token).toBe('t2')
})

// ---- 18. 401 persistant après refresh réussi → escalade, sans 2e refresh ------------------

test('token_401_persists_after_successful_refresh_escalates', async () => {
  seedAuth()
  const tokenCalls = onToken([401, 401])
  const refreshCalls: number[] = []
  server.use(
    http.post(`${API}/auth/refresh`, () => {
      // refresh RÉUSSIT (vrai JWT → pas de refresh préemptif immédiat), mais le 2e POST /sse/token
      // échoue encore → escalade sans 2e refresh.
      refreshCalls.push(1)
      return HttpResponse.json({
        access_token: makeTestJwt({ exp: Math.floor(Date.now() / 1000) + 900 }),
        refresh_token: 'rt2',
        token_type: 'bearer',
      })
    }),
  )
  const streamCalls = onStream(() => sseChannel().response)
  active = createSseClient()
  active.start()
  await until(() => active!.getState() === 'unauthenticated')
  expect(tokenCalls).toHaveLength(2)
  expect(refreshCalls).toHaveLength(1) // un seul refresh, pas de 2e tentative
  expect(streamCalls).toHaveLength(0)
})

// ---- 19. Aucun token/URL loggé sur les chemins d'erreur ------------------------------------

test('no_token_in_logs', async () => {
  seedAuth()
  const spies = [
    vi.spyOn(console, 'error').mockImplementation(() => {}),
    vi.spyOn(console, 'warn').mockImplementation(() => {}),
    vi.spyOn(console, 'log').mockImplementation(() => {}),
  ]
  onToken([{ token: 'super-secret-token' }, { token: 'super-secret-token' }])
  let call = 0
  onStream(() => {
    call += 1
    return call === 1 ? new HttpResponse(null, { status: 401 }) : sseChannel().response
  })
  active = createSseClient()
  active.start()
  await until(() => active!.getState() === 'open')
  for (const s of spies) {
    for (const c of s.mock.calls) {
      expect(JSON.stringify(c)).not.toContain('super-secret-token')
      expect(JSON.stringify(c)).not.toContain('?token=')
    }
    s.mockRestore()
  }
})
