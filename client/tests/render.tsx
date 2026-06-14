import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'

import { AuthProvider } from '@/app/auth-provider'
import { routeTree } from '@/routeTree.gen'

import { seedAuth } from './auth'

interface RenderOptions {
  /** Monte le VRAI routeur de l'app à cette URL (teste la résolution de routes / 404). */
  route?: string
  /**
   * 'authenticated' (défaut) : pré-amorce le token-store → la garde racine `beforeLoad` passe.
   * 'none' : aucun seed → teste la garde (redirection vers /login).
   */
  auth?: 'authenticated' | 'none'
}

/**
 * Rendu de test partagé.
 *
 * - avec `route` : monte le VRAI arbre de boot (AuthProvider → routeur, memory history) sur l'URL.
 *   AuthProvider hydrate depuis le storage (VIDE en test → ne touche pas le store seedé et passe
 *   `ready`), donc les tests routés traversent le chemin prod réel (garde incluse), pas « vert par
 *   foi ». `auth` pilote le seed du token-store.
 * - sans `route` : rend `ui` isolément (tests de composant/feature).
 */
export function renderWithProviders(
  ui: ReactNode,
  { route, auth = 'authenticated' }: RenderOptions = {},
) {
  if (route !== undefined) {
    if (auth === 'authenticated') seedAuth() // token-store peuplé → garde beforeLoad passe
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({ initialEntries: [route] }),
    })
    return render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )
  }
  return render(<>{ui}</>)
}
