// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'

import { AuthProvider } from '@/app/auth-provider'
import { getToken } from '@/lib/powersync/auth-token'
import { tokenStore } from '@/lib/auth/token-store'
import { STORAGE_KEYS } from '@/lib/storage/types'
import { makeTestJwt } from '@tests/auth'
import { server } from '@tests/msw/server'

const API = 'http://localhost:8000'

// Enfant qui CAPTURE le token vu à son tout premier render (mount) — prouve l'ordering : la garde
// `beforeLoad` (sync getToken) verra le token hydraté avant de monter quoi que ce soit.
function TokenAtMount({ sink }: { sink: (t: string | null) => void }) {
  sink(getToken())
  return <span data-testid="child">monté</span>
}

test('storage VIDE → enfants montés après hydratation, non authentifié', async () => {
  render(
    <AuthProvider>
      <span data-testid="child">monté</span>
    </AuthProvider>,
  )
  // null tant que !ready → l'enfant apparaît une fois l'hydratation résolue.
  expect(await screen.findByTestId('child')).toBeInTheDocument()
  expect(tokenStore.get()).toBeNull()
})

test('storage PEUPLÉ (access valide) → mémoire hydratée AVANT le 1er render des enfants', async () => {
  const access = makeTestJwt({ exp: Math.floor(Date.now() / 1000) + 900 })
  localStorage.setItem(STORAGE_KEYS.jwt, access)
  localStorage.setItem(STORAGE_KEYS.refreshToken, 'rt')

  let tokenAtMount: string | null = 'unset'
  render(
    <AuthProvider>
      <TokenAtMount sink={(t) => (tokenAtMount = t)} />
    </AuthProvider>,
  )

  await screen.findByTestId('child')
  expect(tokenAtMount).toBe(access) // getToken() peuplé dès le mount de l'enfant
  expect(tokenStore.getAccessToken()).toBe(access)
})

test('storage peuplé, access EXPIRÉ → refresh au boot ; si 401 → non-auth, enfants quand même montés', async () => {
  const expired = makeTestJwt({ exp: Math.floor(Date.now() / 1000) - 10 }) // déjà expiré
  localStorage.setItem(STORAGE_KEYS.jwt, expired)
  localStorage.setItem(STORAGE_KEYS.refreshToken, 'rt')

  let refreshCalled = 0
  server.use(
    http.post(`${API}/auth/refresh`, () => {
      refreshCalled++
      return new HttpResponse(null, { status: 401 }) // refresh refusé → session morte
    }),
  )

  render(
    <AuthProvider>
      <span data-testid="child">monté</span>
    </AuthProvider>,
  )

  expect(await screen.findByTestId('child')).toBeInTheDocument()
  expect(refreshCalled).toBe(1) // refresh déclenché au boot
  expect(tokenStore.get()).toBeNull() // 401 → purge → non authentifié
})
