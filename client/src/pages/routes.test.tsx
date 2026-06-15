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

const PROTECTED = [
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
