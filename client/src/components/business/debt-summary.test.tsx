// @vitest-environment jsdom
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { expect, test, vi } from 'vitest'

import { useDebtSummary } from '@/hooks/use-debt-summary'
import { useAuth } from '@/hooks/useAuth'

import { DebtSummary } from './debt-summary'

// `DebtSummary` compose un seul hook de lecture — l'agrégation (signe, `HAVING net != 0`, SC-02a
// / SC-02c) est déjà prouvée isolément dans queries.test.ts. On double la FRONTIÈRE (le hook),
// pas l'implémentation interne du composant, même patron que balance-panel.test.tsx.
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/use-debt-summary', () => ({ useDebtSummary: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseDebtSummary = vi.mocked(useDebtSummary)

function stubAuth(userId = 'u1') {
  mockUseAuth.mockReturnValue({
    userId,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  })
}

interface NetRow {
  counterpartyId: string
  counterpartyName: string
  netCents: number
}

function stubDebtSummary(
  data: NetRow[],
  overrides: Partial<ReturnType<typeof useDebtSummary>> = {},
) {
  mockUseDebtSummary.mockReturnValue({
    data,
    isLoading: false,
    isFetching: false,
    error: undefined,
    ...overrides,
  })
}

// `DebtRow` (ligne peuplée ET état vide) rend un VRAI `Link` (SC-02e) : le routeTree applicatif
// ne compose pas encore ce widget (pas de route hôte) — un routeur minimal dédié, avec une
// destination `/debts` réelle, suffit à exercer la navigation sans mocker `@tanstack/react-router`
// (qui rendrait le test tautologique).
function renderRouted(ui: ReactNode) {
  const rootRoute = createRootRoute()
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => ui,
  })
  const debtsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/debts',
    component: () => <p>Dettes</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, debtsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  render(<RouterProvider router={router} />)
  return router
}

// Même convention que format.test.ts / balance-panel.test.tsx : `Intl.NumberFormat('fr-FR')`
// rend une espace fine insécable (U+202F) comme séparateur de milliers et une espace insécable
// (U+00A0) avant `€`.
const THIN_NBSP = ' '
const NBSP = ' '

test('SC-02b — net négatif : « vous devez », signe -, icône et couleur destructive', async () => {
  stubAuth()
  stubDebtSummary([{ counterpartyId: 'u2', counterpartyName: 'Bob', netCents: -5000 }])

  renderRouted(<DebtSummary />)

  const row = await screen.findByRole('listitem') // le routeur résout le match hors-render initial
  expect(row.textContent).toContain('Bob')
  expect(row.textContent).toContain(`vous devez -50,00${NBSP}€`)
  expect(row.querySelector('.text-destructive')).not.toBeNull()
  const icon = row.querySelector('svg.lucide-arrow-down-right') // icône doublant le sens
  expect(icon).not.toBeNull()
  expect(icon).toHaveAttribute('aria-hidden', 'true')
})

test('SC-02b — net positif : « vous prête », signe +, icône et couleur succès', async () => {
  stubAuth()
  stubDebtSummary([{ counterpartyId: 'u3', counterpartyName: 'Chloé', netCents: 5000 }])

  renderRouted(<DebtSummary />)

  const row = await screen.findByRole('listitem')
  expect(row.textContent).toContain('Chloé')
  expect(row.textContent).toContain(`vous prête +50,00${NBSP}€`)
  expect(row.querySelector('.text-success')).not.toBeNull()
  const icon = row.querySelector('svg.lucide-arrow-up-right')
  expect(icon).not.toBeNull()
  expect(icon).toHaveAttribute('aria-hidden', 'true')
})

test('SC-02d — le montant est formaté en EUR fr-FR (séparateur de milliers, virgule décimale)', async () => {
  stubAuth()
  stubDebtSummary([{ counterpartyId: 'u2', counterpartyName: 'Bob', netCents: 123456 }])

  renderRouted(<DebtSummary />)

  const row = await screen.findByRole('listitem')
  expect(row.textContent).toContain(`+1${THIN_NBSP}234,56${NBSP}€`)
})

test('SC-02e — un clic sur une ligne navigue vers /debts filtré sur la contrepartie de la ligne', async () => {
  stubAuth()
  stubDebtSummary([{ counterpartyId: 'u2', counterpartyName: 'Bob', netCents: -5000 }])
  const user = userEvent.setup()

  const router = renderRouted(<DebtSummary />)
  await user.click(await screen.findByRole('link', { name: /bob/i }))

  expect(router.state.location.pathname).toBe('/debts')
  expect(router.state.location.search).toEqual({ with: 'u2' })
})

test('SC-02f — état chargement : la primitive Skeleton est rendue', () => {
  stubAuth()
  stubDebtSummary([], { isLoading: true, isFetching: true })

  const { container } = render(<DebtSummary />)

  expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
})

test('SC-02f — état vide : message et action de navigation, aucun formulaire', async () => {
  stubAuth()
  stubDebtSummary([])

  renderRouted(<DebtSummary />)

  expect(await screen.findByText(/aucune dette/i)).toBeInTheDocument()
  const cta = screen.getByRole('link', { name: /voir les dettes/i })
  expect(cta).toBeInTheDocument()
  expect(screen.queryByRole('form')).not.toBeInTheDocument()
  expect(document.querySelector('form')).not.toBeInTheDocument()
})

test('SC-02f — état erreur : un message d’erreur est rendu quand la requête échoue', () => {
  stubAuth()
  stubDebtSummary([], { error: new Error('boom') })

  render(<DebtSummary />)

  expect(screen.getByRole('alert')).toHaveTextContent(/impossible de charger les dettes/i)
})

test('SC-02f — état peuplé : chaque contrepartie au net non nul est rendue en ligne', async () => {
  stubAuth()
  stubDebtSummary([
    { counterpartyId: 'u2', counterpartyName: 'Bob', netCents: -5000 },
    { counterpartyId: 'u3', counterpartyName: 'Chloé', netCents: 5000 },
  ])

  renderRouted(<DebtSummary />)

  const rows = await screen.findAllByRole('listitem')
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Bob')
  expect(rows[1]).toHaveTextContent('Chloé')
})
