// @vitest-environment node
// Teste les query factories contre une vraie base SQLite (better-sqlite3 in-memory) — c'est
// ICI qu'est portée la réactivité de l'AC (ré-éval après écriture locale). La db better-sqlite3
// (sync) est un double de la db PowerSync (async) : même query-builder Drizzle, cast de test.
import { readFileSync, readdirSync } from 'node:fs'

import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import { beforeEach, describe, expect, test } from 'vitest'

import { selectAccountBalance, selectDebtsForUser, selectTransactions } from './queries'
import type { SQLiteDatabase } from './types'

function loadDdl(): string {
  const file = readdirSync('drizzle').find((f) => f.endsWith('.sql'))
  if (!file) throw new Error('drizzle/*.sql introuvable — lancer `npm run db:generate`')
  return readFileSync(`drizzle/${file}`, 'utf8')
}
const DDL = loadDdl()

let sqlite: Database.Database
let db: SQLiteDatabase

beforeEach(() => {
  sqlite = new Database(':memory:')
  sqlite.exec(DDL)
  db = drizzle(sqlite) as unknown as SQLiteDatabase
})

// --- Seeds en SQL brut (colonnes utiles ; NOT NULL non testées reçoivent une valeur factice). ---

function seedTx(o: {
  id: string
  account_id: string
  date: string
  state: string
  voided_at?: string | null
  category_id?: string | null
}): void {
  sqlite
    .prepare(
      `INSERT INTO transactions (id, account_id, date, state, created_by, created_at, tags,
         debt_generation_override, voided_at, category_id)
       VALUES (@id, @account_id, @date, @state, 'u', '2026-01-01T00:00:00Z', '[]', 'default',
         @voided_at, @category_id)`,
    )
    .run({ voided_at: null, category_id: null, ...o })
}

function seedSplit(o: {
  id: string
  transaction_id: string
  account_id: string
  amount_cents: number
}): void {
  sqlite
    .prepare(
      `INSERT INTO splits (id, transaction_id, account_id, amount_cents, currency, leg_role)
       VALUES (@id, @transaction_id, @account_id, @amount_cents, 'EUR', 'classification')`,
    )
    .run(o)
}

function seedDebt(o: {
  id: string
  from_user_id: string
  to_user_id: string
  created_at: string
  account_id?: string | null
  source_transaction_id?: string | null
}): void {
  sqlite
    .prepare(
      `INSERT INTO debts (id, from_user_id, to_user_id, amount_cents, currency, account_id,
         source_transaction_id, origin, share_ratio, created_at)
       VALUES (@id, @from_user_id, @to_user_id, 1000, 'EUR', @account_id, @source_transaction_id,
         'personal_share_request', '1.0000', @created_at)`,
    )
    .run({ account_id: null, source_transaction_id: null, ...o })
}

describe('selectTransactions', () => {
  test('filtre par compte et par état ; tri date desc', async () => {
    seedTx({ id: 't1', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    seedTx({ id: 't2', account_id: 'a1', date: '2026-03-01', state: 'draft' })
    seedTx({ id: 't3', account_id: 'a2', date: '2026-02-01', state: 'confirmed' })

    const a1 = await selectTransactions(db, { accountId: 'a1' })
    expect(a1.map((t) => t.id)).toEqual(['t2', 't1']) // date desc, a2 exclu

    const confirmed = await selectTransactions(db, { accountId: 'a1', state: 'confirmed' })
    expect(confirmed.map((t) => t.id)).toEqual(['t1']) // draft exclu
  })

  test('f = {} → toutes les lignes (and(undefined,…) ne casse pas le WHERE)', async () => {
    seedTx({ id: 't1', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    seedTx({ id: 't2', account_id: 'a2', date: '2026-01-02', state: 'draft' })

    expect(await selectTransactions(db, {})).toHaveLength(2)
  })
})

describe('selectAccountBalance (D8)', () => {
  test('ne somme que les splits confirmés non annulés', async () => {
    seedTx({ id: 'tc', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    seedTx({ id: 'td', account_id: 'a1', date: '2026-01-02', state: 'draft' })
    seedTx({ id: 'tv', account_id: 'a1', date: '2026-01-03', state: 'confirmed', voided_at: '2026-01-04' })
    seedSplit({ id: 's1', transaction_id: 'tc', account_id: 'a1', amount_cents: 1000 })
    seedSplit({ id: 's2', transaction_id: 'td', account_id: 'a1', amount_cents: 5000 }) // draft → exclu
    seedSplit({ id: 's3', transaction_id: 'tv', account_id: 'a1', amount_cents: 9999 }) // void → exclu

    const rows = await selectAccountBalance(db, 'a1')
    expect(rows[0]?.balanceCents).toBe(1000)
  })

  test('compte sans split → solde 0 (coalesce)', async () => {
    const rows = await selectAccountBalance(db, 'vide')
    expect(rows[0]?.balanceCents).toBe(0)
  })
})

describe('selectDebtsForUser', () => {
  test('renvoie créancier OU débiteur, exclut les tierces', async () => {
    seedDebt({ id: 'd1', from_user_id: 'u1', to_user_id: 'u2', created_at: '2026-01-01' }) // u1 débiteur
    seedDebt({ id: 'd2', from_user_id: 'u3', to_user_id: 'u1', created_at: '2026-01-02' }) // u1 créancier
    seedDebt({ id: 'd3', from_user_id: 'u3', to_user_id: 'u2', created_at: '2026-01-03' }) // tierce

    const rows = await selectDebtsForUser(db, 'u1')
    expect(rows.map((d) => d.id).sort()).toEqual(['d1', 'd2'])
  })

  test('lit une dette débiteur masquée (account_id/source_transaction_id NULL) sans throw', async () => {
    seedDebt({
      id: 'd1',
      from_user_id: 'u1',
      to_user_id: 'u2',
      account_id: null,
      source_transaction_id: null,
      created_at: '2026-01-01',
    })

    const rows = await selectDebtsForUser(db, 'u1')
    expect(rows[0]?.account_id).toBeNull()
    expect(rows[0]?.source_transaction_id).toBeNull()
  })
})

describe('réactivité au niveau requête (AC)', () => {
  test('ré-exécuter après INSERT reflète la nouvelle ligne (N → N+1)', async () => {
    seedTx({ id: 't1', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    expect(await selectTransactions(db, { accountId: 'a1' })).toHaveLength(1)

    seedTx({ id: 't2', account_id: 'a1', date: '2026-01-02', state: 'confirmed' })
    expect(await selectTransactions(db, { accountId: 'a1' })).toHaveLength(2)
  })
})
