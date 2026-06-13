import { createRootRoute, Outlet } from '@tanstack/react-router'

// Layout racine du routeur (file-based). La nav réelle arrivera avec les features
// (S14.6+) ; ici un simple Outlet + un 404 par défaut.
export const Route = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: () => <p>Page introuvable (404)</p>,
})
