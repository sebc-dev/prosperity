import { screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi, type MockInstance } from 'vitest'

import { renderWithProviders } from '@tests/render'

// __root enveloppe désormais l'Outlet dans <PowerSyncProvider> (S14.4) → on substitue le
// singleton client.ts par le mock (pas de wasm/OPFS en jsdom) ; le provider monte donc ses
// contextes sans connexion réelle.
vi.mock('@/lib/powersync/client')

// Anti-régression : depuis S15.1 le __root n'est PLUS QUE des providers (ThemeProvider →
// PowerSyncProvider → Outlet → Toaster) — le header/nav a migré dans la route de layout
// `_authenticated` (AppLayout, P15.1.2). renderWithProviders({route:'/'}) monte ce VRAI root et
// traverse la garde `_authenticated` (session seedée par défaut) jusqu'au placeholder dashboard ;
// on prouve qu'il monte sans throw ni erreur console (pas « vert par foi »). La présence du header
// (toggle…) est re-testée dans components/layout/app-layout.test.tsx (P15.1.2).
let consoleError: MockInstance<typeof console.error>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  consoleError.mockRestore()
})

test('le __root (providers + Outlet + Toaster) monte via le routeur, sans erreur', async () => {
  renderWithProviders(null, { route: '/' })

  // La route `/` protégée rend son placeholder → preuve que les providers ont monté et que la
  // garde a laissé passer (session seedée par défaut).
  expect(await screen.findByRole('heading', { name: /tableau de bord/i })).toBeInTheDocument()
  expect(consoleError).not.toHaveBeenCalled()
})
