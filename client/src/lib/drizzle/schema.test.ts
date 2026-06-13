// @vitest-environment node
// better-sqlite3 = addon natif Node : on applique le DDL généré par drizzle-kit à une base
// SQLite en mémoire et on introspecte via PRAGMA. jsdom ne sait pas exécuter SQLite (env node).
// (tests/setup.ts garde ses accès DOM derrière `typeof document` → inerte ici.)
import { readFileSync, readdirSync } from 'node:fs'

import Database from 'better-sqlite3'
import { beforeAll, describe, expect, test } from 'vitest'

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

interface ColumnInfo {
  name: string
  type: string
  notnull: number
  pk: number
}

let db: Database.Database

function tableNames(): string[] {
  const rows = db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all() as Array<{
    name: string
  }>
  return rows.map((r) => r.name).filter((n) => !n.startsWith('sqlite_'))
}

function tableInfo(table: string): ColumnInfo[] {
  return db.prepare(`PRAGMA table_info(${table})`).all() as ColumnInfo[]
}

function columnNames(table: string): string[] {
  return tableInfo(table).map((c) => c.name)
}

function col(table: string, name: string): ColumnInfo {
  const found = tableInfo(table).find((c) => c.name === name)
  if (!found) throw new Error(`colonne ${table}.${name} absente`)
  return found
}

beforeAll(() => {
  // Applique le SQL COMMITÉ (drizzle/*.sql) → prouve qu'il est valide (AC : « drizzle-kit
  // génère un schéma SQLite sans erreur »). Un drift schema.ts↔SQL est détecté par la garde
  // `git diff --exit-code drizzle/` (plan §5), pas par ce test.
  const sqlFile = readdirSync('drizzle').find((f) => f.endsWith('.sql'))
  if (!sqlFile) throw new Error('drizzle/*.sql introuvable — lancer `npm run db:generate`')
  const ddl = readFileSync(`drizzle/${sqlFile}`, 'utf8')
  db = new Database(':memory:')
  db.exec(ddl) // throw si le DDL est invalide
})

describe('schéma Drizzle local — mirror des sync rules (P14.3.1)', () => {
  test('déclare exactement les 11 tables synchronisées', () => {
    expect(new Set(tableNames())).toEqual(new Set(EXPECTED_TABLES))
  })

  test('aucune table server-only / non publiée n’apparaît', () => {
    const present = new Set(tableNames())
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

  test('masquage débiteur (D4) : colonnes masquées NULLABLE', () => {
    // 0 = nullable, 1 = NOT NULL (PRAGMA table_info).
    expect(col('debts', 'account_id').notnull).toBe(0)
    expect(col('debts', 'source_transaction_id').notnull).toBe(0)
    expect(col('share_requests', 'source_transaction_id').notnull).toBe(0)
    // Contre-exemple : une colonne non masquée reste NOT NULL.
    expect(col('debts', 'amount_cents').notnull).toBe(1)
  })

  test('debts = exactement 10 colonnes, materialization_trace ABSENTE', () => {
    const cols = columnNames('debts')
    expect(cols).toHaveLength(10)
    expect(cols).not.toContain('materialization_trace')
  })

  test('users_public minimale {id, display_name, role} (anti-fuite PII)', () => {
    expect(new Set(columnNames('users_public'))).toEqual(new Set(['id', 'display_name', 'role']))
  })

  test('affinités de type (D3) : montants integer, ratios Decimal en text', () => {
    // PRAGMA renvoie le type DÉCLARÉ ; SQLite le normalise en majuscules → compare insensible à la casse.
    const typeOf = (table: string, name: string) => col(table, name).type.toLowerCase()
    expect(typeOf('debts', 'amount_cents')).toBe('integer')
    expect(typeOf('debts', 'share_ratio')).toBe('text')
    expect(typeOf('account_members', 'default_share_ratio')).toBe('text')
    expect(typeOf('budgets', 'carry_over_remainder')).toBe('integer')
  })
})
