import type { SQLiteDatabase } from '@/lib/drizzle/types'
import { asPowerSync, createMockPowerSync } from '@tests/mocks/powersync'

// Manual mock Vitest de `client.ts` : substitue le singleton PowerSync (wasm/OPFS, indisponible
// en jsdom) par le `MockPowerSyncDatabase`. Activé par `vi.mock('@/lib/powersync/client')` dans
// tout test qui monte le VRAI __root (tests routés). Le provider y résout ses deux contextes sans
// instancier de connexion réelle. (Le test du provider lui-même fournit sa propre factory.)
const mock = createMockPowerSync()
const drizzle = { __stub: 'drizzle' } as unknown as SQLiteDatabase

export const getPowerSync = () => asPowerSync(mock)
export const getDrizzle = () => drizzle
