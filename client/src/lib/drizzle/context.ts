import { createContext, use } from 'react'

import type { SQLiteDatabase } from './types'

// Contexte fournissant la db Drizzle (PowerSync-wrappée). Le PROVIDER réel est posé en
// S14.4 (`wrapPowerSyncWithDrizzle` + provider) ; en S14.3 on expose le contexte + le hook,
// consommés en test via un provider stub (gabarit `useTheme`, S14.2).
export const DrizzleContext = createContext<SQLiteDatabase | null>(null)

export function useDrizzle(): SQLiteDatabase {
  const db = use(DrizzleContext)
  if (!db) throw new Error('useDrizzle doit être utilisé dans un <DrizzleContext value={…}>')
  return db
}
