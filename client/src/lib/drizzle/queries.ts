import { and, desc, eq, isNull, or, sql } from 'drizzle-orm'

import type { Transaction } from './index'
import { debts, splits, transactions } from './schema'
import type { SQLiteDatabase } from './types'

export interface TransactionFilters {
  accountId?: string
  state?: Transaction['state']
  categoryId?: string
}

// Query factories PURES : `(db, args) => requête Drizzle`. La db est INJECTÉE (better-sqlite3
// en test, db PowerSync-wrappée en S14.4) ; la requête est compilable par `toCompilableQuery`
// côté hook, et c'est l'unité que le watch PowerSync ré-invoque (réactivité, cf. queries.test).

// f = {} → `and(undefined, undefined, undefined)` → Drizzle omet le WHERE (toutes les lignes).
export const selectTransactions = (db: SQLiteDatabase, f: TransactionFilters = {}) =>
  db
    .select()
    .from(transactions)
    .where(
      and(
        f.accountId ? eq(transactions.account_id, f.accountId) : undefined,
        f.state ? eq(transactions.state, f.state) : undefined,
        f.categoryId ? eq(transactions.category_id, f.categoryId) : undefined,
      ),
    )
    .orderBy(desc(transactions.date))

// Solde réel (D8) : Σ des splits du compte, joints aux transactions `confirmed` non annulées
// (hypothèse mono-devise, ADR 0008). `coalesce(..., 0)` → 0 si aucun split.
// `voided_at IS NULL` est une défense en profondeur : le backend pose `state='void'` ET
// `voided_at` atomiquement, donc `state='confirmed'` implique déjà `voided_at IS NULL` —
// mais aucune contrainte ne le garantit côté SQLite local (D5), d'où le second prédicat.
export const selectAccountBalance = (db: SQLiteDatabase, accountId: string) =>
  db
    .select({ balanceCents: sql<number>`coalesce(sum(${splits.amount_cents}), 0)` })
    .from(splits)
    .innerJoin(transactions, eq(splits.transaction_id, transactions.id))
    .where(
      and(
        eq(splits.account_id, accountId),
        eq(transactions.state, 'confirmed'),
        isNull(transactions.voided_at),
      ),
    )

// Dettes où l'utilisateur est partie prenante (créancier `to_user_id` OU débiteur `from_user_id`).
export const selectDebtsForUser = (db: SQLiteDatabase, userId: string) =>
  db
    .select()
    .from(debts)
    .where(or(eq(debts.from_user_id, userId), eq(debts.to_user_id, userId)))
    .orderBy(desc(debts.created_at))
