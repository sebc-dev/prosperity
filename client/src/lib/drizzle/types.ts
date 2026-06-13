import type { PowerSyncSQLiteDatabase } from '@powersync/drizzle-driver'

import * as schema from './schema'

// Type de la db Drizzle consommée par les query factories et les hooks.
// En PRODUCTION (S14.4) c'est la db PowerSync-wrappée (`wrapPowerSyncWithDrizzle`, ASYNC) —
// c'est le `result-kind` async qui rend les queries compatibles `toCompilableQuery`.
// En test, une db `better-sqlite3` (sync) sert de double : même surface de query-builder
// Drizzle, seul le `result-kind` diffère → cast de test (`as unknown as SQLiteDatabase`).
export type SQLiteDatabase = PowerSyncSQLiteDatabase<typeof schema>
