import { PowerSyncContext } from '@powersync/react'
import { useEffect, useMemo, type ReactNode } from 'react'

import { DrizzleContext } from '@/lib/drizzle/context'
import { connector } from '@/lib/powersync/connector'
import { getDrizzle, getPowerSync } from '@/lib/powersync/client'

// Provider racine de la couche données : fournit la `PowerSyncDatabase` (réactivité,
// `useStatus`/`useQuery`) ET la db Drizzle wrappée (`useDrizzle`, S14.3) sur la MÊME
// instance singleton. Monté sous `ThemeProvider` dans __root.
export function PowerSyncProvider({ children }: { children: ReactNode }) {
  // Mémoïsés → une seule instanciation, stable sous StrictMode (le singleton de client.ts
  // garantit déjà l'unicité ; useMemo évite un re-wrap Drizzle à chaque rendu).
  const ps = useMemo(getPowerSync, [])
  const db = useMemo(getDrizzle, [])

  // connect/disconnect idempotents. Sous StrictMode le cycle est connect→disconnect→connect :
  // l'état CONNECTÉ est stable en fin de cycle (pas « connect appelé une seule fois »).
  useEffect(() => {
    void ps.connect(connector)
    return () => {
      void ps.disconnect()
    }
  }, [ps])

  return (
    <PowerSyncContext value={ps}>
      <DrizzleContext value={db}>{children}</DrizzleContext>
    </PowerSyncContext>
  )
}
