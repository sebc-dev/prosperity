// @vitest-environment jsdom
import { screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// __root monte PowerSyncProvider → mock du singleton (pas de wasm/OPFS).
vi.mock('@/lib/powersync/client')

test('sans session, une route protégée (/) redirige vers /login', async () => {
  renderWithProviders(null, { route: '/', auth: 'none' })
  // La garde racine `beforeLoad` (getToken() null) redirige → le form de connexion s'affiche.
  expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument()
  // Le showcase de la home n'est PAS rendu (on a bien été éjecté).
  expect(screen.queryByRole('heading', { name: /composants/i })).not.toBeInTheDocument()
})

test('/login est accessible sans session', async () => {
  renderWithProviders(null, { route: '/login', auth: 'none' })
  expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument()
})

test('/setup est accessible sans session (flux ouvert)', async () => {
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  expect(await screen.findByLabelText('Nom du foyer')).toBeInTheDocument()
})

test('avec session, la route protégée (/) rend la home', async () => {
  renderWithProviders(null, { route: '/', auth: 'authenticated' })
  expect(await screen.findByRole('heading', { name: /composants/i })).toBeInTheDocument()
})
