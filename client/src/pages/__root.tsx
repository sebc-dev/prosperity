import { createRootRoute, Outlet } from '@tanstack/react-router'

import { PowerSyncProvider } from '@/app/powersync-provider'
import { ThemeProvider } from '@/app/theme-provider'
import { Toaster } from '@/components/ui/sonner'

// Layout racine : PROVIDERS uniquement. Le ThemeProvider enveloppe toute l'app (thème + toggle
// disponibles partout) ; le PowerSyncProvider (couche données PowerSync + Drizzle, S14.4) est
// monté sous le thème ; le Toaster (Sonner) y est monté une fois.
//
// La garde d'auth et le chrome applicatif (header + navigation) ne vivent PAS ici : ils sont
// portés par la route de layout `_authenticated` (P15.1.x). Conséquence : les écrans publics
// (login / setup / accept-invite) sont rendus NUS, sans nav ni header.
export const Route = createRootRoute({
  component: () => (
    <ThemeProvider>
      <PowerSyncProvider>
        <Outlet />
        <Toaster />
      </PowerSyncProvider>
    </ThemeProvider>
  ),
  notFoundComponent: () => <p>Page introuvable (404)</p>,
})
