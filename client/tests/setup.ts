import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'

import { tokenStore } from '@/lib/auth/token-store'

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

  // Radix DropdownMenu/Popper (menu user, S15.1+) s'appuie sur des API du DOM que jsdom
  // n'implémente pas → sans ces stubs, ouvrir le menu (clic/clavier) throw. Posé une fois ici
  // (réutilisé par toute primitive Radix-Popper d'E15).
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
    Element.prototype.setPointerCapture = () => {}
    Element.prototype.releasePointerCapture = () => {}
    Element.prototype.scrollIntoView = () => {}
  }
  if (!('ResizeObserver' in globalThis)) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

// MSW intercepte au niveau RÉSEAU. `onUnhandledRequest: 'error'` fait échouer tout
// appel non mocké (anti faux-vert, cf. tests/msw-guard.test.ts).
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  // Purge le token-store mémoire entre tests (anti-fuite : un `login()` laisserait un token
  // peuplé visible du test suivant). On reset via le LEAF `token-store` (zéro import) et NON via
  // `session.ts` : ce dernier tire `lib/storage` → `@aparajita/capacitor-secure-storage`, dont
  // l'import eager casserait le `vi.mock(...)` de `storage.test.ts`. Un éventuel `setTimeout` de
  // refresh resté armé devient INOFFENSIF après ce reset : au tir, `refresh()` ne trouve plus de
  // refresh token → purge locale, AUCUN appel réseau (pas de faux-rouge sous onUnhandledRequest:error).
  tokenStore.set(null)
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
