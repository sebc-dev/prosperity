import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'

import { routeTree } from '@/routeTree.gen'

interface RenderOptions {
  /** Monte le VRAI routeur de l'app à cette URL (teste la résolution de routes / 404). */
  route?: string
}

/**
 * Rendu de test partagé, extensible (un `queryClient` pourra s'ajouter en S14.3/S14.6
 * sans réécriture des appelants).
 *
 * - avec `route` : monte le routeur de l'app (memory history) sur l'URL donnée ;
 * - sans `route` : rend `ui` isolément (tests de composant/feature).
 */
export function renderWithProviders(ui: ReactNode, { route }: RenderOptions = {}) {
  if (route !== undefined) {
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({ initialEntries: [route] }),
    })
    return render(<RouterProvider router={router} />)
  }
  return render(<>{ui}</>)
}
