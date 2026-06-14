// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { tokenStore } from '@/lib/auth/token-store'
import { makeTestJwt, seedAuth } from '@tests/auth'
import { server } from '@tests/msw/server'

function Probe() {
  const { isAuthenticated, userId } = useAuth()
  return (
    <div>
      <span data-testid="auth">{String(isAuthenticated)}</span>
      <span data-testid="uid">{userId ?? 'none'}</span>
    </div>
  )
}

test('dérive isAuthenticated/userId du token-store et se RE-REND sur set hors-React', async () => {
  render(<Probe />)
  expect(screen.getByTestId('auth').textContent).toBe('false')
  expect(screen.getByTestId('uid').textContent).toBe('none')

  // `set` hors-React (ex. login dans session.ts) → useSyncExternalStore re-rend.
  seedAuth({
    accessToken: makeTestJwt({ sub: 'user-7', exp: Math.floor(Date.now() / 1000) + 900 }),
  })
  expect(await screen.findByText('user-7')).toBeInTheDocument()
  expect(screen.getByTestId('auth').textContent).toBe('true')

  tokenStore.set(null) // logout hors-React → repasse non-authentifié
  expect(await screen.findByText('none')).toBeInTheDocument()
  expect(screen.getByTestId('auth').textContent).toBe('false')
})

test('expose login/logout/refresh (actions de session.ts)', async () => {
  let api: ReturnType<typeof useAuth> | undefined
  function Capture() {
    api = useAuth()
    return null
  }
  render(<Capture />)
  expect(typeof api?.login).toBe('function')
  expect(typeof api?.logout).toBe('function')
  expect(typeof api?.refresh).toBe('function')

  // Le hook délègue bien à session.login (bout-en-bout via MSW).
  server.use(
    http.post('http://localhost:8000/auth/login', () =>
      HttpResponse.json({
        access_token: makeTestJwt({ sub: 'u1', exp: Math.floor(Date.now() / 1000) + 900 }),
        refresh_token: 'rt',
        token_type: 'bearer',
      }),
    ),
  )
  await api?.login('a@b.c', 'pw')
  expect(tokenStore.getAccessToken()).toBeTruthy()
})
