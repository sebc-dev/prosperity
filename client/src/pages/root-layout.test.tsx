import { screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// Anti-régression (M4) : le nouveau __root enveloppe l'Outlet dans <ThemeProvider>
// (→ matchMedia/localStorage) + <Toaster/>. renderWithProviders({route}) monte ce
// VRAI root ; les tests S14.1 routés (not-found…) le traversent → on ne le tient
// pas « vert par foi », on prouve qu'il monte sans throw ni erreur console.
let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  consoleError.mockRestore()
})

test('le layout racine (ThemeProvider + toggle + Toaster) monte via le routeur', async () => {
  renderWithProviders(null, { route: '/' })

  // Le toggle vit dans __root → sa présence prouve que ThemeProvider/Toaster ont monté.
  expect(await screen.findByRole('button', { name: /thème/i })).toBeInTheDocument()
  expect(consoleError).not.toHaveBeenCalled()
})
