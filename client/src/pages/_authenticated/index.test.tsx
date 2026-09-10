// @vitest-environment jsdom
import { screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// Tests routés (même patron que root-layout.test.tsx / app-layout.test.tsx) : mock du singleton
// PowerSync (pas de wasm/OPFS) + stub de `useCurrentUser` (nav) — le mock client PowerSync
// n'expose pas de db Drizzle interrogeable par useQuery.
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
  useCurrentUser: () => ({
    user: { id: 'u1', display_name: 'Alice', role: 'member' },
    isAdmin: false,
  }),
}))

// Les hooks de lecture du BalancePanel (S15.3 ticket 01) sont doublés À LA FRONTIÈRE, sur le
// modèle de balance-panel.test.tsx : SANS ces stubs, `selectVisibleAccounts` échoue au rendu sur
// le mock client, `BalanceErrorBoundary` avale l'erreur et la route rendrait un widget
// entièrement en échec — indiscernable du succès si l'on n'assertait que `aria-label="Solde"`
// (`BalanceError` porte la même section). D'où un compte NON VIDE et un solde réel ci-dessous :
// ce test échoue si le widget tombe dans son fallback.
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    userId: 'u1',
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}))
vi.mock('@/hooks/use-visible-accounts', () => ({
  useVisibleAccounts: () => ({
    data: [{ id: 'a1', name: 'Compte courant', type: 'courant', currency: 'EUR' }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  }),
}))
vi.mock('@/hooks/use-account-balance', () => ({
  useAccountBalance: () => ({
    balanceCents: 123456,
    data: [{ balanceCents: 123456 }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  }),
}))
vi.mock('@/hooks/use-sync-status', () => ({
  useSyncStatus: () => ({ state: 'synced', lastSyncedAt: new Date() }),
}))

// Même convention que format.test.ts : `Intl.NumberFormat('fr-FR')` rend une espace fine
// insécable (U+202F) comme séparateur de milliers et une espace insécable (U+00A0) avant `€`.
const THIN_NBSP = '\u202f'
const NBSP = '\u00a0'

test('SC-01a — la route / rend le tableau de bord (plus le placeholder), dans la coque _authenticated', async () => {
  renderWithProviders(null, { route: '/' })

  // Le vrai tableau de bord (widget BalancePanel), pas le placeholder « à venir ».
  expect(await screen.findByRole('heading', { name: /tableau de bord/i })).toBeInTheDocument()
  expect(screen.queryByText(/à venir/i)).not.toBeInTheDocument()

  // Le widget rend son CONTENU (une ligne de compte + son montant), pas seulement sa coquille :
  // on se place DANS la section « Solde » (la nav de la coque porte elle aussi des `listitem`).
  const panel = screen.getByLabelText('Solde') // section BalancePanel
  const row = within(panel).getByRole('listitem')
  expect(row).toHaveTextContent('Compte courant')
  // `textContent` brut (pas `toHaveTextContent`, qui normalise `\s+` et effacerait la preuve).
  expect(row.textContent).toContain(`1${THIN_NBSP}234,56${NBSP}€`)
  // …et le fallback d'échec (BalanceError / BalanceErrorBoundary) n'est PAS rendu.
  expect(screen.queryByText(/impossible de charger les soldes/i)).not.toBeInTheDocument()

  // Coque `_authenticated` : header (logo) + navigation entourent le contenu de la route.
  expect(screen.getByText('Prosperity')).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: 'Navigation principale' })).toBeInTheDocument()
})
