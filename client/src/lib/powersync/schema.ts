import { DrizzleAppSchema } from '@powersync/drizzle-driver'

import * as drizzleSchema from '@/lib/drizzle/schema'

// Schéma PowerSync DÉRIVÉ du schéma Drizzle (S14.3) — source unique des tables locales
// (pas de redéclaration manuelle des colonnes). `DrizzleAppSchema` traduit les `sqliteTable`
// en `Schema` PowerSync consommé par `PowerSyncDatabase` (client.ts).
export const powerSyncSchema = new DrizzleAppSchema(drizzleSchema)
