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

// Dette nette par contrepartie (SC-02a) : agrège les rows `debts` déjà matérialisées (ADR-0002 —
// dettes = projection serveur, aucun recalcul de la dette elle-même ici) où l'utilisateur est
// partie prenante (même prédicat WHERE que `selectDebtsForUser`, pas dupliqué en deux requêtes
// créancier/débiteur séparées). Un CASE WHEN pivote, PAR ROW, le signe du montant (créancier
// `to_user_id` → `+amount_cents`, débiteur `from_user_id` → `-amount_cents`) et détermine la
// contrepartie (l'AUTRE partie de la row) ; un GROUP BY somme ces montants signés par
// contrepartie. `HAVING net != 0` masque en SQL les contreparties au net nul (SC-02c) — pas un
// filtre côté JS après coup. Convention de signe exposée : positif = l'utilisateur est créancier
// net (« vous prête »), négatif = débiteur net (« vous devez »), cf. `debt-summary.tsx`.
// Le nom d'affichage vient d'une jointure à `users_public` (même patron que `selectUserById`,
// colonnes synchronisées, ADR-0003) sur la sous-requête déjà agrégée — pas une jointure avant
// agrégation, qui dupliquerait les lignes `debts` par contrepartie.
export const selectNetDebtsByCounterparty = (db: SQLiteDatabase, userId: string) => {
  const counterpartyId = sql<string>`case when ${debts.from_user_id} = ${userId} then ${debts.to_user_id} else ${debts.from_user_id} end`
  const netCents = sql<number>`sum(case when ${debts.to_user_id} = ${userId} then ${debts.amount_cents} else -${debts.amount_cents} end)`

  const netByCounterparty = db
    .select({
      counterpartyId: counterpartyId.as('counterparty_id'),
      netCents: netCents.as('net_cents'),
    })
    .from(debts)
    .where(or(eq(debts.from_user_id, userId), eq(debts.to_user_id, userId)))
    .groupBy(counterpartyId)
    .having(sql`${netCents} != 0`)
    .as('net_by_counterparty')

  return db
    .select({
      counterpartyId: netByCounterparty.counterpartyId,
      counterpartyName: users_public.display_name,
      netCents: netByCounterparty.netCents,
    })
    .from(netByCounterparty)
    .innerJoin(users_public, eq(users_public.id, netByCounterparty.counterpartyId))
    .orderBy(users_public.display_name)
}
