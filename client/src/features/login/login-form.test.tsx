// @vitest-environment jsdom
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { expect, test, vi } from 'vitest'

import { getToken } from '@/lib/powersync/auth-token'
import { renderWithProviders } from '@tests/render'
import { server } from '@tests/msw/server'

const API = 'http://localhost:8000'

// __root monte PowerSyncProvider → substitue le singleton par le mock (pas de wasm/OPFS en jsdom).
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
  // AppLayout (rendu par _authenticated) consomme useCurrentUser → on le stube (le mock client
  // PowerSync n'expose pas de db Drizzle interrogeable par useQuery).
  useCurrentUser: () => ({
    user: { id: 'u1', display_name: 'Alice', role: 'member' },
    isAdmin: false,
  }),
}))

async function fillAndSubmit() {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'admin@foyer.fr')
  await user.type(screen.getByLabelText('Mot de passe'), 'motdepasse123')
  await user.click(screen.getByRole('button', { name: /se connecter/i }))
}

test('login OK : POST /auth/login → token stocké → navigation vers /', async () => {
  // route /login SANS session : on teste le parcours login lui-même (auth: 'none').
  renderWithProviders(null, { route: '/login', auth: 'none' })
  await fillAndSubmit()

  // Le handler par défaut (/auth/login → TokenPair) peuple le token, puis navigate({ to: '/' }).
  await waitFor(() => expect(getToken()).toBeTruthy())
  // Après navigation, la home (tableau de bord) est rendue → preuve de la redirection bout-en-bout.
  expect(await screen.findByRole('heading', { name: /tableau de bord/i })).toBeInTheDocument()
})

test('login KO (401) : message role="alert" générique, pas de crash, bouton réactivé', async () => {
  server.use(http.post(`${API}/auth/login`, () => new HttpResponse(null, { status: 401 })))
  renderWithProviders(null, { route: '/login', auth: 'none' })
  await fillAndSubmit()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Identifiants invalides.')
  expect(getToken()).toBeNull()
  expect(screen.getByRole('button', { name: /se connecter/i })).toBeEnabled()
})

test('erreur réseau (non-401) : message générique, pas de crash', async () => {
  server.use(http.post(`${API}/auth/login`, () => HttpResponse.error()))
  renderWithProviders(null, { route: '/login', auth: 'none' })
  await fillAndSubmit()

  expect(await screen.findByRole('alert')).toHaveTextContent('Identifiants invalides.')
  expect(getToken()).toBeNull()
})

test('bouton désactivé pendant la requête (état pending)', async () => {
  // Handler qui ne résout jamais → le bouton reste disabled le temps de la requête.
  server.use(http.post(`${API}/auth/login`, () => new Promise(() => {})))
  renderWithProviders(null, { route: '/login', auth: 'none' })
  await fillAndSubmit()

  await waitFor(() => expect(screen.getByRole('button', { name: /se connecter/i })).toBeDisabled())
})
