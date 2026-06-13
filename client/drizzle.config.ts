import { defineConfig } from 'drizzle-kit'

// Dialecte SQLite = cible PowerSync côté client. `drizzle-kit generate` émet le DDL
// déterministe sous `drizzle/` (commité, testé en appliquant le SQL à better-sqlite3).
// On retient `generate`+commit plutôt que `push` (qui pousse vers une DB live, hors-sujet
// côté client PowerSync) — divergence vs AC#2 actée au DoD (cf. plan D9).
export default defineConfig({
  dialect: 'sqlite',
  schema: './src/lib/drizzle/schema.ts',
  out: './drizzle',
})
