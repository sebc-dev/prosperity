import { createRootRoute, Outlet } from '@tanstack/react-router'

import { PowerSyncProvider } from '@/app/powersync-provider'
import { ThemeProvider } from '@/app/theme-provider'
import { SyncStatusBadge } from '@/components/business/sync-status-badge'
import { ThemeToggle } from '@/components/theme-toggle'
import { Toaster } from '@/components/ui/sonner'

// Layout racine du routeur (file-based). Le ThemeProvider enveloppe toute l'app
// (le toggle est visible partout) ; le PowerSyncProvider (couche données : PowerSync +
// Drizzle, S14.4) est monté SOUS le thème (→ le badge de synchro lit son statut) ; le
// Toaster (Sonner) y est monté une fois.
export const Route = createRootRoute({
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
