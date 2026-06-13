import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'

import { server } from './msw/server'

// jsdom n'implémente pas matchMedia : le ThemeProvider (readInitial) l'appelle.
// Défaut « clair » (matches:false) ; surchargeable par test (branche fallback M3),
// puis restauré en afterEach.
export function stubMatchMedia(matches = false) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches,
    media: '',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })
}
stubMatchMedia()

// jsdom n'implémente pas scrollTo : TanStack Router l'appelle à la navigation
// (warning console). Polyfill no-op → silence le bruit pour tous les tests routés.
window.scrollTo = vi.fn()

// MSW intercepte au niveau RÉSEAU. `onUnhandledRequest: 'error'` fait échouer tout
// appel non mocké (anti faux-vert, cf. tests/msw-guard.test.ts).
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  cleanup() // démonte les composants Testing Library
  server.resetHandlers() // purge les handlers ad-hoc (anti-fuite d'état inter-tests)
  // <html> et window sont PARTAGÉS entre tests d'un fichier : sans ces resets, la
  // classe `.dark`, la clé thème et une surcharge matchMedia(matches:true) fuiteraient.
  document.documentElement.classList.remove('dark')
  localStorage.clear()
  stubMatchMedia() // restaure le défaut clair (annule une surcharge M3)
})
afterAll(() => {
  server.close()
})
