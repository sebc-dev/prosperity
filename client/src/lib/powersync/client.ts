import { wrapPowerSyncWithDrizzle } from '@powersync/drizzle-driver'
import { PowerSyncDatabase } from '@powersync/web'

import * as schema from '@/lib/drizzle/schema'

import { powerSyncSchema } from './schema'

// Singleton module-level (D3) : une SEULE `PowerSyncDatabase` pour toute l'app, même
// sous StrictMode (le provider mémoïse `getPowerSync`/`getDrizzle`). Pas de point
// d'injection naturel → les tests substituent CE module via `vi.mock('@/lib/powersync/client')`.
let _ps: PowerSyncDatabase | null = null

export function getPowerSync(): PowerSyncDatabase {
  _ps ??= new PowerSyncDatabase({
    schema: powerSyncSchema,
    database: { dbFilename: 'prosperity.db' },
  })
  return _ps
}

// La db Drizzle (ASYNC) consommée par les query factories/hooks (S14.3), wrappée sur
// la même `PowerSyncDatabase` que le contexte → une seule connexion sous-jacente.
export const getDrizzle = () => wrapPowerSyncWithDrizzle(getPowerSync(), { schema })
