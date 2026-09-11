// @vitest-environment jsdom
import { screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// __root monte PowerSyncProvider → mock du singleton (pas de wasm/OPFS).
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
  // AppLayout (rendu par _authenticated) consomme useCurrentUser → on le stube (le mock client
  // PowerSync n'expose pas de db Drizzle interrogeable par useQuery).
  useCurrentUser: () => ({
    user: { id: 'u1', display_name: 'Alice', role: 'member' },
    isAdmin: false,
  }),
}))

// La route `/` rend BalancePanel (S15.3, ticket 01), qui interroge la db Drizzle via
// useVisibleAccounts — même limite que useCurrentUser ci-dessus (mock client, pas de vraie db) :
// stubé en état vide pour que ces montages routés cessent de rendre un widget en échec
// silencieux (le widget lui-même est couvert par balance-panel.test.tsx).
vi.mock('@/hooks/use-visible-accounts', () => ({
  useVisibleAccounts: () => ({ data: [], isLoading: false, error: undefined }),
}))

// useDebtSummary — même limite que useVisibleAccounts ci-dessus (mock client, pas de vraie db) :
// stubé en état vide pour que ces montages routés cessent de rendre un widget en échec silencieux.
vi.mock('@/hooks/use-debt-summary', () => ({
  useDebtSummary: () => ({ data: [], isLoading: false, isFetching: false, error: undefined }),
}))

test('sans session, une route protégée (/) redirige vers /login', async () => {
  renderWithProviders(null, { route: '/', auth: 'none' })
  // La garde `_authenticated.beforeLoad` (getToken() null) redirige → le form de connexion s'affiche.
  expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument()
  // Le tableau de bord protégé n'est PAS rendu (on a bien été éjecté).
  expect(screen.queryByRole('heading', { name: /tableau de bord/i })).not.toBeInTheDocument()
})

test('/login est accessible sans session', async () => {
  renderWithProviders(null, { route: '/login', auth: 'none' })
  expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument()
})

test('/setup est accessible sans session (flux ouvert)', async () => {
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  expect(await screen.findByLabelText('Nom du foyer')).toBeInTheDocument()
})

test('avec session, la route protégée (/) rend le tableau de bord', async () => {
  renderWithProviders(null, { route: '/', auth: 'authenticated' })
  expect(await screen.findByRole('heading', { name: /tableau de bord/i })).toBeInTheDocument()
})
