import { and, desc, eq, inArray, isNull, or, sql } from 'drizzle-orm'

import type { Transaction } from './index'
import { account_members, accounts, debts, splits, transactions, users_public } from './schema'
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

// Comptes visibles par un membre du foyer : perso (`owner_id = userId`) OU commun (le membre
// figure dans `account_members`), hors archivés (D14/dashboard). Le SOLDE n'est volontairement
// PAS ré-agrégé ici : chaque ligne est ensuite passée à `selectAccountBalance` (réutilisée telle
// quelle, une requête par compte, cf. `useAccountBalance`) — pas de duplication de la logique
// « confirmed & non annulé » (D8), qui reste portée par une seule fonction.
export const selectVisibleAccounts = (db: SQLiteDatabase, userId: string) =>
  db
    .select({
      id: accounts.id,
      name: accounts.name,
      type: accounts.type,
      currency: accounts.currency,
    })
    .from(accounts)
    .where(
      and(
        isNull(accounts.archived_at),
        or(
          eq(accounts.owner_id, userId),
          inArray(
            accounts.id,
            db
              .select({ account_id: account_members.account_id })
              .from(account_members)
              .where(eq(account_members.user_id, userId)),
          ),
        ),
      ),
    )
    .orderBy(accounts.name)

// Ligne `users_public` d'un utilisateur (id, display_name, role) — synchronisée (sync rule
// `household`). `id = ''` (utilisateur courant inconnu) → 0 ligne (la query reste valide pour
// `useQuery`, qui exige une CompilableQuery non-nulle ; le fail-safe RBAC en découle).
export const selectUserById = (db: SQLiteDatabase, id: string) =>
  db.select().from(users_public).where(eq(users_public.id, id)).limit(1)

// Dettes où l'utilisateur est partie prenante (créancier `to_user_id` OU débiteur `from_user_id`).
export const selectDebtsForUser = (db: SQLiteDatabase, userId: string) =>
  db
    .select()
    .from(debts)
    .where(or(eq(debts.from_user_id, userId), eq(debts.to_user_id, userId)))
    .orderBy(desc(debts.created_at))
