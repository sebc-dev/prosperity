import { createRootRoute, Outlet, redirect } from '@tanstack/react-router'

import { PowerSyncProvider } from '@/app/powersync-provider'
import { ThemeProvider } from '@/app/theme-provider'
import { SyncStatusBadge } from '@/components/business/sync-status-badge'
import { ThemeToggle } from '@/components/theme-toggle'
import { Toaster } from '@/components/ui/sonner'
import { getToken } from '@/lib/powersync/auth-token'

// Layout racine du routeur (file-based). Le ThemeProvider enveloppe toute l'app
// (le toggle est visible partout) ; le PowerSyncProvider (couche données : PowerSync +
// Drizzle, S14.4) est monté SOUS le thème (→ le badge de synchro lit son statut) ; le
// Toaster (Sonner) y est monté une fois.
export const Route = createRootRoute({
  // Garde d'auth MINIMALE : lecture SYNC `getToken()` (fiable car AuthProvider hydrate le
  // token-store AVANT de monter le routeur, cf. main.tsx). Pas de session → redirige `/login`,
  // SAUF `/login` & `/setup` (parcours sans JWT préalable). La garde per-écran + RBAC = E15.
  beforeLoad: ({ location }) => {
    const open = location.pathname === '/login' || location.pathname === '/setup'
    // `redirect()` lève un objet Redirect (contrat TanStack), pas une Error → exception au lint.
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    if (!open && !getToken()) throw redirect({ to: '/login' })
  },
  component: () => (
    <ThemeProvider>
      <PowerSyncProvider>
        <header className="flex items-center justify-end gap-4 p-4">
          <SyncStatusBadge />
          <ThemeToggle />
        </header>
        <main className="p-4">
          <Outlet />
        </main>
        <Toaster />
      </PowerSyncProvider>
    </ThemeProvider>
  ),
  notFoundComponent: () => <p>Page introuvable (404)</p>,
})
