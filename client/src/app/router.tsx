import { createRouter } from '@tanstack/react-router'

import { routeTree } from '@/routeTree.gen'

export const router = createRouter({ routeTree })

// Rend le routeur type-safe de bout en bout (routes, params, search).
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
