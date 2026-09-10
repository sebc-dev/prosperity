// @vitest-environment jsdom
import { screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { useAccountBalance } from '@/hooks/use-account-balance'
import { useSyncStatus } from '@/hooks/use-sync-status'
import { useVisibleAccounts } from '@/hooks/use-visible-accounts'
import { useAuth } from '@/hooks/useAuth'
import { renderWithProviders } from '@tests/render'

import { BalancePanel } from './balance-panel'

// `BalancePanel` compose plusieurs hooks de lecture (D8) : on double la FRONTIÈRE (les hooks
// eux-mêmes, déjà testés isolément — use-account-balance.test.tsx, use-sync-status.test.tsx),
// pas l'implémentation interne du composant. `userId` est stubé (résolution réelle hors périmètre,
// dépend de S14.6).
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/use-visible-accounts', () => ({ useVisibleAccounts: vi.fn() }))
vi.mock('@/hooks/use-account-balance', () => ({ useAccountBalance: vi.fn() }))
vi.mock('@/hooks/use-sync-status', () => ({ useSyncStatus: vi.fn() }))

// `Link` (état vide, SC-01g) exige un routeur réel → ces deux mocks permettent de monter le VRAI
// __root/_authenticated (même patron que root-layout.test.tsx) pour CE cas précis.
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
  useCurrentUser: () => ({
    user: { id: 'u1', display_name: 'Alice', role: 'member' },
    isAdmin: false,
  }),
}))

const mockUseAuth = vi.mocked(useAuth)
const mockUseVisibleAccounts = vi.mocked(useVisibleAccounts)
const mockUseAccountBalance = vi.mocked(useAccountBalance)
const mockUseSyncStatus = vi.mocked(useSyncStatus)

function stubAuth(userId = 'u1') {
  mockUseAuth.mockReturnValue({
    userId,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  })
}

// Un seul compte visible : les cas ci-dessous portent sur l'état d'UNE ligne (`type` en `as const`
// pour rester dans l'union de `selectVisibleAccounts`, pas un `string` élargi).
const ONE_ACCOUNT = [
  { id: 'a1', name: 'Compte courant', type: 'courant' as const, currency: 'EUR' },
]

function stubVisibleAccounts(data = ONE_ACCOUNT) {
  mockUseVisibleAccounts.mockReturnValue({
    data,
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
}

test('SC-01f — chaque ligne de compte affiche « synchronisé il y a X min »', () => {
  stubAuth()
  mockUseVisibleAccounts.mockReturnValue({
    data: [
      { id: 'a1', name: 'Compte courant', type: 'courant', currency: 'EUR' },
      { id: 'a2', name: 'Livret', type: 'livret', currency: 'EUR' },
    ],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  mockUseAccountBalance.mockReturnValue({
    balanceCents: 4200,
    data: [{ balanceCents: 4200 }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  const fiveMinAgo = new Date(Date.now() - 5 * 60_000)
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: fiveMinAgo })

  renderWithProviders(<BalancePanel />)

  const freshnessLabels = screen.getAllByText('synchronisé il y a 5 min')
  expect(freshnessLabels).toHaveLength(2) // une par ligne de compte
})

// Même convention que format.test.ts : `Intl.NumberFormat('fr-FR')` rend une espace fine insécable
// (U+202F) comme séparateur de milliers et une espace insécable (U+00A0) avant `€`.
const THIN_NBSP = '\u202f'
const NBSP = '\u00a0'

test('SC-01f — chaque ligne de compte affiche le nom du compte et son montant formaté', () => {
  stubAuth()
  mockUseVisibleAccounts.mockReturnValue({
    data: [
      { id: 'a1', name: 'Compte courant', type: 'courant', currency: 'EUR' },
      { id: 'a2', name: 'Livret', type: 'livret', currency: 'EUR' },
    ],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  // Solde distinct par compte (clé = accountId) : prouve que CHAQUE ligne porte SA requête (D8)
  // et pas un même solde recopié ; ≥ 1000 € sur a1 pour couvrir le séparateur de milliers.
  const balances: Record<string, number> = { a1: 123456, a2: 4200 }
  mockUseAccountBalance.mockImplementation((accountId) => ({
    balanceCents: balances[accountId] ?? 0,
    data: [{ balanceCents: balances[accountId] ?? 0 }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  }))
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: new Date() })

  renderWithProviders(<BalancePanel />)

  const rows = screen.getAllByRole('listitem')
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Compte courant')
  expect(rows[1]).toHaveTextContent('Livret')
  // `textContent` brut (pas `toHaveTextContent`, qui normalise `\s+` en espace ASCII et
  // effacerait la preuve) : les caractères fr-FR réellement rendus, U+202F et U+00A0.
  expect(rows[0]?.textContent).toContain(`1${THIN_NBSP}234,56${NBSP}€`)
  expect(rows[1]?.textContent).toContain(`42,00${NBSP}€`)
})

test('SC-01g — état chargement : la primitive Skeleton est rendue', () => {
  stubAuth()
  mockUseVisibleAccounts.mockReturnValue({
    data: [],
    isLoading: true,
    isFetching: true,
    error: undefined,
  })
  mockUseSyncStatus.mockReturnValue({ state: 'syncing', lastSyncedAt: undefined })

  const { container } = renderWithProviders(<BalancePanel />)

  expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
})

test('SC-01g — état vide : message + action de navigation, aucun formulaire', async () => {
  stubAuth()
  mockUseVisibleAccounts.mockReturnValue({
    data: [],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: undefined })

  renderWithProviders(null, { route: '/' })

  expect(await screen.findByText(/aucun compte/i)).toBeInTheDocument()
  // CTA de navigation (un lien, PAS un bouton de soumission de formulaire).
  const cta = screen.getByRole('link', { name: /créer un compte/i })
  expect(cta).toBeInTheDocument()
  expect(screen.queryByRole('form')).not.toBeInTheDocument()
  expect(document.querySelector('form')).not.toBeInTheDocument()
})

test('SC-01h — état erreur : un message d’erreur est rendu quand la requête échoue', () => {
  stubAuth()
  mockUseVisibleAccounts.mockReturnValue({
    data: [],
    isLoading: false,
    isFetching: false,
    error: new Error('boom'),
  })
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: undefined })

  renderWithProviders(<BalancePanel />)

  expect(screen.getByRole('alert')).toHaveTextContent(/impossible de charger les soldes/i)
})

// Fraîcheur — les deux autres branches de `formatFreshness`, sur une ligne de compte
// RÉELLEMENT rendue (pas un test unitaire de la fonction, qui n'est pas exportée).
test("SC-01f — sous la minute, la ligne affiche « à l'instant » (pas « il y a 0 min »)", () => {
  stubAuth()
  stubVisibleAccounts()
  mockUseAccountBalance.mockReturnValue({
    balanceCents: 4200,
    data: [{ balanceCents: 4200 }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: new Date() })

  renderWithProviders(<BalancePanel />)

  const row = screen.getByRole('listitem')
  // Libellé exact imposé par docs/ui/screens-dashboard.md § Copy FR, apostrophe ASCII (U+0027).
  expect(within(row).getByText("à l'instant")).toBeInTheDocument()
  expect(row).toHaveTextContent('Compte courant')
})

test('SC-01f — sans synchro préalable, la ligne affiche « pas encore synchronisé »', () => {
  stubAuth()
  stubVisibleAccounts()
  mockUseAccountBalance.mockReturnValue({
    balanceCents: 4200,
    data: [{ balanceCents: 4200 }],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
  mockUseSyncStatus.mockReturnValue({ state: 'syncing', lastSyncedAt: undefined })

  renderWithProviders(<BalancePanel />)

  const row = screen.getByRole('listitem')
  expect(within(row).getByText('pas encore synchronisé')).toBeInTheDocument()
  expect(row).toHaveTextContent('Compte courant')
})

// Échec / chargement du solde D'UNE LIGNE : dégrade cette ligne seule (le widget reste rendu),
// et n'affiche JAMAIS un « 0,00 € » fabriqué (défaut `?? 0` de `useAccountBalance`).
test('SC-01h — solde en échec : la ligne annonce « Solde indisponible », sans montant', () => {
  stubAuth()
  stubVisibleAccounts()
  mockUseAccountBalance.mockReturnValue({
    balanceCents: 0,
    data: [],
    isLoading: false,
    isFetching: false,
    error: new Error('boom'),
  })
  mockUseSyncStatus.mockReturnValue({ state: 'synced', lastSyncedAt: undefined })

  renderWithProviders(<BalancePanel />)

  const row = screen.getByRole('listitem')
  expect(within(row).getByRole('alert')).toHaveTextContent('Solde indisponible')
  expect(row.textContent).not.toContain('€') // aucun montant, surtout pas « 0,00 € »
  expect(row).toHaveTextContent('Compte courant') // le compte reste identifiable
})

test('SC-01g — solde en chargement : la ligne rend un Skeleton à la place du montant', () => {
  stubAuth()
  stubVisibleAccounts()
  mockUseAccountBalance.mockReturnValue({
    balanceCents: 0,
    data: [],
    isLoading: true,
    isFetching: true,
    error: undefined,
  })
  mockUseSyncStatus.mockReturnValue({ state: 'syncing', lastSyncedAt: undefined })

  renderWithProviders(<BalancePanel />)

  const row = screen.getByRole('listitem')
  expect(row.querySelectorAll('[data-slot="skeleton"]').length).toBe(1)
  expect(row.textContent).not.toContain('€') // aucun montant tant que la requête court
  expect(row).toHaveTextContent('Compte courant')
})
