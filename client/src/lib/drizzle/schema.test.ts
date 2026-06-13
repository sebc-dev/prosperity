// @vitest-environment node
// Deux niveaux d'assertion :
//  1. le DDL généré par drizzle-kit (drizzle/*.sql) s'applique à SQLite sans erreur (AC#1) —
//     via better-sqlite3 (addon natif Node ; jsdom n'exécute pas SQLite).
//  2. la STRUCTURE (tables, colonnes, nullabilité du masquage, types) est introspectée
//     directement sur `schema.ts` via getTableConfig — SOURCE DE VÉRITÉ. Ainsi un drift
//     schema.ts↔SQL généré ne peut PAS masquer ces invariants (notamment le masquage D4),
//     même sans la garde CI `git diff drizzle/` (déférée S14.7).
// (tests/setup.ts garde ses accès DOM derrière `typeof document` → inerte en env node.)
import { readFileSync, readdirSync } from 'node:fs'

import Database from 'better-sqlite3'
import { type SQLiteTable, getTableConfig } from 'drizzle-orm/sqlite-core'
import { describe, expect, test } from 'vitest'

import * as schema from './schema'

// Les 11 tables RÉELLEMENT publiées (download) par powersync/sync_rules.yaml.
const EXPECTED_TABLES = [
  'accounts',
  'account_members',
  'transactions',
  'splits',
  'categories',
  'budgets',
  'budget_contributors',
  'debts',
  'share_requests',
  'settlement_lines',
  'users_public',
]

// Tables server-only / non publiées : ne doivent JAMAIS apparaître côté client (note ⚠️ #207,
// ADR 0003). `materialization_trace` est exclue au niveau colonne (cf. debts ci-dessous).
const FORBIDDEN_TABLES = [
  'admin_audit_logs',
  'sync_request_log',
  'pending_actions',
  'settlements',
  'savings_goals',
  'savings_goal_allocations',
  'notifications',
  'budget_threshold_alerts',
  'users',
]

// Introspection du schéma TS (pas du SQL figé) → source de vérité réellement consommée par
// les types/hooks.
const configs = (Object.values(schema) as SQLiteTable[]).map((t) => getTableConfig(t))

function table(name: string) {
  const cfg = configs.find((c) => c.name === name)
  if (!cfg) throw new Error(`table ${name} absente du schéma`)
  return cfg
}
function columnNames(name: string): string[] {
  return table(name).columns.map((c) => c.name)
}
function col(tableName: string, colName: string) {
  const c = table(tableName).columns.find((column) => column.name === colName)
  if (!c) throw new Error(`colonne ${tableName}.${colName} absente`)
  return c
}

describe('schéma Drizzle local — mirror des sync rules (P14.3.1)', () => {
  test('le DDL généré (drizzle/*.sql) est un schéma SQLite valide (AC#1)', () => {
    const sqlFile = readdirSync('drizzle').find((f) => f.endsWith('.sql'))
    if (!sqlFile) throw new Error('drizzle/*.sql introuvable — lancer `npm run db:generate`')
    const ddl = readFileSync(`drizzle/${sqlFile}`, 'utf8')
    const db = new Database(':memory:')
    expect(() => db.exec(ddl)).not.toThrow()
    const tables = (
      db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all() as Array<{
        name: string
      }>
    )
      .map((r) => r.name)
      .filter((n) => !n.startsWith('sqlite_'))
    expect(new Set(tables)).toEqual(new Set(EXPECTED_TABLES))
    db.close()
  })

  test('schema.ts déclare exactement les 11 tables synchronisées', () => {
    expect(new Set(configs.map((c) => c.name))).toEqual(new Set(EXPECTED_TABLES))
  })

  test('aucune table server-only / non publiée n’apparaît', () => {
    const present = new Set(configs.map((c) => c.name))
    for (const forbidden of FORBIDDEN_TABLES) {
      expect(present.has(forbidden)).toBe(false)
    }
  })

  test('colonnes clés présentes', () => {
    expect(columnNames('transactions')).toEqual(
      expect.arrayContaining(['account_id', 'state', 'tags']),
    )
    expect(columnNames('splits')).toEqual(
      expect.arrayContaining(['account_id', 'amount_cents', 'leg_role']),
    )
    expect(columnNames('budgets')).toContain('carry_over_remainder')
  })

  test('masquage débiteur (D4) : colonnes masquées NULLABLE, masquage CIBLÉ', () => {
    // notNull=false → la colonne accepte NULL (vue débiteur des sync rules livre NULL AS …).
    expect(col('debts', 'account_id').notNull).toBe(false)
    expect(col('debts', 'source_transaction_id').notNull).toBe(false)
    expect(col('share_requests', 'source_transaction_id').notNull).toBe(false)
    // Contre-exemples : le masquage est CIBLÉ, pas global (sinon l'invariant serait trivial).
    expect(col('debts', 'amount_cents').notNull).toBe(true)
    expect(col('share_requests', 'short_label').notNull).toBe(true)
  })

  test('debts = exactement les 10 colonnes projetées (materialization_trace ABSENTE)', () => {
    expect(new Set(columnNames('debts'))).toEqual(
      new Set([
        'id',
        'from_user_id',
        'to_user_id',
        'amount_cents',
        'currency',
        'account_id',
        'source_transaction_id',
        'origin',
        'share_ratio',
        'created_at',
      ]),
    )
  })

  test('users_public minimale {id, display_name, role} (anti-fuite PII)', () => {
    expect(new Set(columnNames('users_public'))).toEqual(new Set(['id', 'display_name', 'role']))
  })

  test('affinités de type (D3) : montants integer, ratios Decimal en text', () => {
    const sqlType = (t: string, n: string) => col(t, n).getSQLType().toLowerCase()
    expect(sqlType('debts', 'amount_cents')).toBe('integer')
    expect(sqlType('debts', 'share_ratio')).toBe('text')
    expect(sqlType('account_members', 'default_share_ratio')).toBe('text')
    expect(sqlType('budgets', 'carry_over_remainder')).toBe('integer')
  })
})
