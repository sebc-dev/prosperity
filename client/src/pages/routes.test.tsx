// @vitest-environment jsdom
import { screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// Tests routés → mock du singleton PowerSync ; `useCurrentUser` stubé (AppLayout l'appelle via
// la nav — le stub du mock client n'est pas une vraie db Drizzle).
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
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

const PROTECTED = [
  ['/', /tableau de bord/i],
  ['/accounts', /comptes/i],
  ['/transactions', /transactions/i],
  ['/budgets', /budgets/i],
  ['/debts', /dettes/i],
  ['/categories', /catégories/i],
  ['/settings', /réglages/i],
] as const

test.each(PROTECTED)(
  'route protégée %s : rendue (placeholder) si authentifié',
  async (route, heading) => {
    renderWithProviders(null, { route, auth: 'authenticated' })
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  },
)

test.each(PROTECTED)(
  'route protégée %s : redirige vers /login si non authentifié',
  async (route) => {
    renderWithProviders(null, { route, auth: 'none' })
    expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument()
  },
)

test('/accept-invite est PUBLIQUE (rendue sans session, hors garde)', async () => {
  renderWithProviders(null, { route: '/accept-invite', auth: 'none' })
  expect(await screen.findByRole('heading', { name: /accepter l.invitation/i })).toBeInTheDocument()
})
