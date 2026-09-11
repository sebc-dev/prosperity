// @vitest-environment node
// Teste les query factories contre une vraie base SQLite (better-sqlite3 in-memory) — c'est
// ICI qu'est portée la réactivité de l'AC (ré-éval après écriture locale). La db better-sqlite3
// (sync) est un double de la db PowerSync (async) : même query-builder Drizzle, cast de test.
import { readFileSync, readdirSync } from 'node:fs'

import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import { beforeEach, describe, expect, test } from 'vitest'

import {
  selectAccountBalance,
  selectDebtsForUser,
  selectNetDebtsByCounterparty,
  selectTransactions,
  selectVisibleAccounts,
} from './queries'
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

function seedAccount(o: { id: string; owner_id?: string | null; archived_at?: string | null }): void {
  sqlite
    .prepare(
      `INSERT INTO accounts (id, household_id, name, type, currency, owner_id, created_at, archived_at)
       VALUES (@id, 'h1', @id, 'courant', 'EUR', @owner_id, '2026-01-01T00:00:00Z', @archived_at)`,
    )
    .run({ owner_id: null, archived_at: null, ...o })
}

function seedAccountMember(o: { id: string; account_id: string; user_id: string }): void {
  sqlite
    .prepare(
      `INSERT INTO account_members (id, account_id, user_id, default_share_ratio, joined_at)
       VALUES (@id, @account_id, @user_id, '0.5000', '2026-01-01T00:00:00Z')`,
    )
    .run(o)
}

function seedDebt(o: {
  id: string
  from_user_id: string
  to_user_id: string
  created_at: string
  amount_cents?: number
  account_id?: string | null
  source_transaction_id?: string | null
}): void {
  sqlite
    .prepare(
      `INSERT INTO debts (id, from_user_id, to_user_id, amount_cents, currency, account_id,
         source_transaction_id, origin, share_ratio, created_at)
       VALUES (@id, @from_user_id, @to_user_id, @amount_cents, 'EUR', @account_id, @source_transaction_id,
         'personal_share_request', '1.0000', @created_at)`,
    )
    .run({ amount_cents: 1000, account_id: null, source_transaction_id: null, ...o })
}

// `users_public` (sync rule `household`) : requis par la jointure du nom de contrepartie
// (`selectNetDebtsByCounterparty`, cf. commentaire de la factory).
function seedUser(o: { id: string; display_name: string; role?: 'admin' | 'member' }): void {
  sqlite
    .prepare(`INSERT INTO users_public (id, display_name, role) VALUES (@id, @display_name, @role)`)
    .run({ role: 'member', ...o })
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
  test('ne somme que les splits confirmés non annulés (couvre les 4 états)', async () => {
    seedTx({ id: 'tc', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    seedTx({ id: 'td', account_id: 'a1', date: '2026-01-02', state: 'draft' })
    seedTx({ id: 'tp', account_id: 'a1', date: '2026-01-03', state: 'planned' })
    seedTx({ id: 'tx', account_id: 'a1', date: '2026-01-04', state: 'void', voided_at: '2026-01-04' })
    // Arête : confirmed PUIS annulé (state reste 'confirmed' mais voided_at posé) → exclu par le 2e prédicat.
    seedTx({ id: 'tcv', account_id: 'a1', date: '2026-01-05', state: 'confirmed', voided_at: '2026-01-06' })
    seedSplit({ id: 's_c', transaction_id: 'tc', account_id: 'a1', amount_cents: 1000 })
    seedSplit({ id: 's_d', transaction_id: 'td', account_id: 'a1', amount_cents: 5000 }) // draft → exclu
    seedSplit({ id: 's_p', transaction_id: 'tp', account_id: 'a1', amount_cents: 7000 }) // planned → exclu
    seedSplit({ id: 's_x', transaction_id: 'tx', account_id: 'a1', amount_cents: 8000 }) // void → exclu
    seedSplit({ id: 's_cv', transaction_id: 'tcv', account_id: 'a1', amount_cents: 9999 }) // annulé → exclu

    const rows = await selectAccountBalance(db, 'a1')
    expect(rows[0]?.balanceCents).toBe(1000)
  })

  test('compte sans split → solde 0 (coalesce)', async () => {
    const rows = await selectAccountBalance(db, 'vide')
    expect(rows[0]?.balanceCents).toBe(0)
  })

  test('SC-01e — le solde = somme des amount_cents des splits confirmés non annulés (0 si aucun split)', async () => {
    expect((await selectAccountBalance(db, 'nouveau'))[0]?.balanceCents).toBe(0)

    seedTx({ id: 't1', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    seedSplit({ id: 's1', transaction_id: 't1', account_id: 'a1', amount_cents: 1500 })
    seedTx({ id: 't2', account_id: 'a1', date: '2026-01-02', state: 'confirmed' })
    seedSplit({ id: 's2', transaction_id: 't2', account_id: 'a1', amount_cents: 2500 })

    expect((await selectAccountBalance(db, 'a1'))[0]?.balanceCents).toBe(4000)
  })
})

describe('selectVisibleAccounts', () => {
  test('SC-01d — liste les comptes perso (owner) et communs (account_members), exclut archivés et tiers', async () => {
    seedAccount({ id: 'owned', owner_id: 'u1' }) // perso de u1 → visible
    seedAccount({ id: 'shared', owner_id: 'other' })
    seedAccountMember({ id: 'm1', account_id: 'shared', user_id: 'u1' }) // membre commun → visible
    seedAccount({ id: 'archived-owned', owner_id: 'u1', archived_at: '2026-02-01' }) // archivé → exclu
    seedAccount({ id: 'foreign', owner_id: 'other2' }) // ni owner ni membre → exclu

    const rows = await selectVisibleAccounts(db, 'u1')
    expect(rows.map((r) => r.id).sort()).toEqual(['owned', 'shared'])
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

describe('selectNetDebtsByCounterparty', () => {
  test('SC-02a — net = somme signée créancier (+) − débiteur (−) des rows debts, par contrepartie', async () => {
    seedUser({ id: 'u2', display_name: 'Bob' })
    seedUser({ id: 'u3', display_name: 'Chloé' })
    // u1 → u2 : u1 débiteur de 3000 (négatif pour u1) ; u2 → u1 : u1 créancier de 1000 (positif) ;
    // net attendu pour u2 = -3000 + 1000 = -2000.
    seedDebt({ id: 'd1', from_user_id: 'u1', to_user_id: 'u2', amount_cents: 3000, created_at: '2026-01-01' })
    seedDebt({ id: 'd2', from_user_id: 'u2', to_user_id: 'u1', amount_cents: 1000, created_at: '2026-01-02' })
    // Tierce (n'implique pas u1) → doit être totalement ignorée de l'agrégation.
    seedDebt({ id: 'd3', from_user_id: 'u2', to_user_id: 'u3', amount_cents: 5000, created_at: '2026-01-03' })
    // u1 créancier net de u3 (2000).
    seedDebt({ id: 'd4', from_user_id: 'u3', to_user_id: 'u1', amount_cents: 2000, created_at: '2026-01-04' })

    const rows = await selectNetDebtsByCounterparty(db, 'u1')

    const byCounterparty = new Map(rows.map((r) => [r.counterpartyId, r]))
    expect(byCounterparty.get('u2')).toEqual({
      counterpartyId: 'u2',
      counterpartyName: 'Bob',
      netCents: -2000,
    })
    expect(byCounterparty.get('u3')).toEqual({
      counterpartyId: 'u3',
      counterpartyName: 'Chloé',
      netCents: 2000,
    })
    expect(rows).toHaveLength(2) // la tierce (d3) n'a créé aucune 3e contrepartie
  })

  test('SC-02c — une contrepartie au net nul n’apparaît pas (HAVING net != 0)', async () => {
    seedUser({ id: 'u2', display_name: 'Bob' })
    seedUser({ id: 'u3', display_name: 'Chloé' })
    // u1 ↔ u2 : dettes croisées de même montant → net exactement 0 pour u2.
    seedDebt({ id: 'd1', from_user_id: 'u1', to_user_id: 'u2', amount_cents: 1000, created_at: '2026-01-01' })
    seedDebt({ id: 'd2', from_user_id: 'u2', to_user_id: 'u1', amount_cents: 1000, created_at: '2026-01-02' })
    // u3 reste au net non nul → prouve que le filtre est sélectif, pas une purge totale.
    seedDebt({ id: 'd3', from_user_id: 'u1', to_user_id: 'u3', amount_cents: 500, created_at: '2026-01-03' })

    const rows = await selectNetDebtsByCounterparty(db, 'u1')

    expect(rows.map((r) => r.counterpartyId)).toEqual(['u3'])
  })
})

// La factory reflète l'état courant de la base : c'est l'unité que le watch PowerSync
// ré-invoque (réactivité réelle = S14.4). Ici on prouve la propriété de base, pas un re-render.
describe('ré-exécution reflète l’état courant local', () => {
  test('ré-exécuter après INSERT reflète la nouvelle ligne (N → N+1)', async () => {
    seedTx({ id: 't1', account_id: 'a1', date: '2026-01-01', state: 'confirmed' })
    expect(await selectTransactions(db, { accountId: 'a1' })).toHaveLength(1)

    seedTx({ id: 't2', account_id: 'a1', date: '2026-01-02', state: 'confirmed' })
    expect(await selectTransactions(db, { accountId: 'a1' })).toHaveLength(2)
  })
})
