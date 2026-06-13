import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'

import { server } from './msw/server'

// `setupFiles` s'exécute pour TOUS les fichiers de test, y compris ceux en
// `// @vitest-environment node` (schéma/queries Drizzle via better-sqlite3), où
// `window`/`document`/`localStorage` n'existent pas. On garde donc les accès DOM
// derrière cette détection ; le bloc MSW reste inconditionnel (fonctionne en node,
// inerte sans requête).
const isDom = typeof document !== 'undefined'

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

if (isDom) {
  stubMatchMedia()
  // jsdom n'implémente pas scrollTo : TanStack Router l'appelle à la navigation
  // (warning console). Polyfill no-op → silence le bruit pour tous les tests routés.
  window.scrollTo = vi.fn()
}

// MSW intercepte au niveau RÉSEAU. `onUnhandledRequest: 'error'` fait échouer tout
// appel non mocké (anti faux-vert, cf. tests/msw-guard.test.ts).
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  server.resetHandlers() // purge les handlers ad-hoc (anti-fuite d'état inter-tests)
  if (isDom) {
    cleanup() // démonte les composants Testing Library
    // <html> et window sont PARTAGÉS entre tests d'un fichier : sans ces resets, la
    // classe `.dark`, la clé thème et une surcharge matchMedia(matches:true) fuiteraient.
    document.documentElement.classList.remove('dark')
    localStorage.clear()
    stubMatchMedia() // restaure le défaut clair (annule une surcharge M3)
  }
})
afterAll(() => {
  server.close()
})
