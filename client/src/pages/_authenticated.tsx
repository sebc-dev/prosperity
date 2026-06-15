import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'

import { AppLayout } from '@/components/layout/app-layout'
import { getToken } from '@/lib/powersync/auth-token'

// Route de layout PATHLESS (`_authenticated` → préfixe `_` = aucun segment d'URL : `/accounts`
// reste `/accounts`). Elle porte la garde d'auth pour TOUTES les routes protégées, qui vivent
// sous `pages/_authenticated/`. Les écrans publics (login / setup / accept-invite) restent au
// top-level, hors de cette garde, et donc rendus NUS (sans le chrome applicatif).
//
// SÉCURITÉ : cette garde est de la NAVIGATION, pas une autorisation de données. Le rempart réel
// est côté serveur (sync rules PowerSync filtrées par `request.user_id()` + authz REST backend).
// Un token présent ≠ données autorisées.
export const Route = createFileRoute('/_authenticated')({
  // `getToken()` est SYNC et fiable : AuthProvider hydrate le token-store AVANT de monter le
  // routeur (cf. main.tsx). Pas de session → redirige `/login`.
  beforeLoad: () => {
    // `redirect()` lève un objet Redirect (contrat TanStack), pas une Error → exception au lint.
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    if (!getToken()) throw redirect({ to: '/login' })
  },
  component: () => (
    <AppLayout>
      <Outlet />
    </AppLayout>
  ),
})
