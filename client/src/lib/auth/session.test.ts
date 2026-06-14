// @vitest-environment jsdom
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { api } from '@/lib/api/client'
import { commitTokens, login, logout, refresh } from '@/lib/auth/session'
import { tokenStore } from '@/lib/auth/token-store'
import { STORAGE_KEYS } from '@/lib/storage/types'
import { makeTestJwt } from '@tests/auth'
import { server } from '@tests/msw/server'

const API = 'http://localhost:8000'

// TokenPair forgé : access = JWT de test (exp décodable), refresh = opaque.
function pair(exp: number, refresh = 'rt-new') {
  return { access_token: makeTestJwt({ exp }), refresh_token: refresh, token_type: 'bearer' }
}
const futureExp = () => Math.floor(Date.now() / 1000) + 900

// Handlers comptés (vérifie qu'UNE requête est bien partie / pas partie).
function loginHandler(respond: () => Response, calls = { n: 0 }) {
  server.use(
    http.post(`${API}/auth/login`, () => {
      calls.n++
      return respond()
    }),
  )
  return calls
}
function refreshHandler(respond: () => Response, calls = { n: 0 }) {
  server.use(
    http.post(`${API}/auth/refresh`, () => {
      calls.n++
      return respond()
    }),
  )
  return calls
}

afterEach(() => {
  vi.useRealTimers()
})

describe('login', () => {
  test('OK → token en mémoire (sync) + storage (access+refresh) + isAuthenticated', async () => {
    loginHandler(() => HttpResponse.json(pair(futureExp(), 'rt-1')))
    await login('a@b.c', 'pw')

    expect(tokenStore.getAccessToken()).toBeTruthy()
    expect(localStorage.getItem(STORAGE_KEYS.jwt)).toBe(tokenStore.getAccessToken())
    expect(localStorage.getItem(STORAGE_KEYS.refreshToken)).toBe('rt-1')
  })

  test('KO (401) → throw invalid_credentials ; mémoire & storage vierges', async () => {
    loginHandler(() => new HttpResponse(null, { status: 401 }))
    await expect(login('a@b.c', 'bad')).rejects.toThrow('invalid_credentials')

    expect(tokenStore.get()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEYS.jwt)).toBeNull()
    expect(localStorage.getItem(STORAGE_KEYS.refreshToken)).toBeNull()
  })

  test('erreur réseau non-401 → propage (pas de token)', async () => {
    loginHandler(() => HttpResponse.error())
    await expect(login('a@b.c', 'pw')).rejects.toThrow()
    expect(tokenStore.get()).toBeNull()
  })
})

describe('refresh', () => {
  test('rotation : nouveau pair remplace mémoire + storage', async () => {
    loginHandler(() => HttpResponse.json(pair(futureExp(), 'rt-old')))
    await login('a@b.c', 'pw')
    const oldAccess = tokenStore.getAccessToken()

    // exp distinct → JWT distinct (makeTestJwt est déterministe) : prouve le remplacement.
    refreshHandler(() => HttpResponse.json(pair(futureExp() + 100, 'rt-rotated')))
    const alive = await refresh()

    expect(alive).toBe(true)
    expect(tokenStore.getAccessToken()).not.toBe(oldAccess)
    expect(tokenStore.get()?.refreshToken).toBe('rt-rotated')
    expect(localStorage.getItem(STORAGE_KEYS.refreshToken)).toBe('rt-rotated')
  })

  test('échec (401) → purge : mémoire null + storage vidé + renvoie false', async () => {
    loginHandler(() => HttpResponse.json(pair(futureExp(), 'rt')))
    await login('a@b.c', 'pw')

    refreshHandler(() => new HttpResponse(null, { status: 401 }))
    const alive = await refresh()

    expect(alive).toBe(false)
    expect(tokenStore.get()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEYS.jwt)).toBeNull()
    expect(localStorage.getItem(STORAGE_KEYS.refreshToken)).toBeNull()
  })

  test('sans refresh en mémoire → purge, 0 appel réseau', async () => {
    // Aucun handler /auth/refresh : onUnhandledRequest:'error' ferait échouer un appel.
    const alive = await refresh()
    expect(alive).toBe(false)
    expect(tokenStore.get()).toBeNull()
  })

  test('single-flight : 2 refresh concurrents → UN seul appel réseau', async () => {
    loginHandler(() => HttpResponse.json(pair(futureExp(), 'rt')))
    await login('a@b.c', 'pw')

    const calls = refreshHandler(() => HttpResponse.json(pair(futureExp(), 'rt2')))
    await Promise.all([refresh(), refresh()])
    expect(calls.n).toBe(1)
  })
})

describe('logout', () => {
  test('avec refresh → POST /auth/logout (204) puis purge', async () => {
    loginHandler(() => HttpResponse.json(pair(futureExp(), 'rt')))
    await login('a@b.c', 'pw')

    let logoutCalled = 0
    server.use(
      http.post(`${API}/auth/logout`, () => {
        logoutCalled++
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await logout()

    expect(logoutCalled).toBe(1)
    expect(tokenStore.get()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEYS.jwt)).toBeNull()
  })

  test('sans refresh en mémoire → purge, 0 appel réseau', async () => {
    // Pas de handler logout : un appel échouerait (onUnhandledRequest:'error').
    await logout()
    expect(tokenStore.get()).toBeNull()
  })
})

describe('auto-refresh préemptif (fake timers)', () => {
  // NB : on n'assertе PAS `vi.getTimerCount()` (MSW/undici planifient leurs propres timers fakés,
  // bruit non déterministe) — on prouve le comportement par les requêtes /auth/refresh émises.
  test('à exp − 60 s un /auth/refresh part seul ; le timer est REPROGRAMMÉ (2ᵉ tir)', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z')) // Date.now() fakée → scheduleRefresh cohérent
    const exp = Math.floor(Date.now() / 1000) + 900 // +15 min

    loginHandler(() => HttpResponse.json(pair(exp, 'rt-0')))
    await login('a@b.c', 'pw') // arme le timer à exp − 60 s = +840 s

    // Chaque refresh renvoie un pair dont l'exp recule de +15 min → un nouveau timer +840 s.
    let i = 0
    const calls = refreshHandler(() => {
      i += 1
      return HttpResponse.json(pair(exp + i * 900, `rt-${i}`))
    })

    await vi.advanceTimersByTimeAsync(840_000) // 1er tir préemptif
    expect(calls.n).toBe(1)
    expect(tokenStore.get()?.refreshToken).toBe('rt-1')

    await vi.advanceTimersByTimeAsync(900_000) // 2ᵉ tir → prouve la reprogrammation
    expect(calls.n).toBe(2)
    expect(tokenStore.get()?.refreshToken).toBe('rt-2')
  })

  test('double-login : pas de fuite de timer (un seul /auth/refresh au déclenchement)', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const exp = Math.floor(Date.now() / 1000) + 900

    loginHandler(() => HttpResponse.json(pair(exp, 'rt')))
    await login('a@b.c', 'pw')
    await login('a@b.c', 'pw') // 2ᵉ login : clearTimeout du 1er → un seul timer armé

    const calls = refreshHandler(() => HttpResponse.json(pair(exp + 900, 'rt2')))
    await vi.advanceTimersByTimeAsync(840_000)

    expect(calls.n).toBe(1) // un seul tir : le timer du 1er login a bien été annulé (pas de fuite)
  })
})

describe('middleware Bearer', () => {
  test('token en store → la requête api.* porte Authorization: Bearer <token>', async () => {
    await commitTokens({ accessToken: 'tok-xyz', refreshToken: 'rt', accessExp: futureExp() })
    let auth: string | null = null
    server.use(
      http.get(`${API}/setup`, ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ status: 'open' })
      }),
    )
    await api.GET('/setup')
    expect(auth).toBe('Bearer tok-xyz')
  })

  test('sans token → header Authorization absent', async () => {
    tokenStore.set(null)
    let auth: string | null = 'sentinel'
    server.use(
      http.get(`${API}/setup`, ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ status: 'open' })
      }),
    )
    await api.GET('/setup')
    expect(auth).toBeNull()
  })
})
