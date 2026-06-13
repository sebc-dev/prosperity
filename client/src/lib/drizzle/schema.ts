import { integer, sqliteTable, text } from 'drizzle-orm/sqlite-core'

// Schéma local SQLite (Drizzle) — mirror des 11 tables RÉELLEMENT synchronisées (download)
// par `powersync/sync_rules.yaml` (S13.7). Source de vérité = les sync rules, pas la roadmap.
//
// Mapping PG→SQLite (D3) : UUID/timestamptz/date/numeric → text ; bigint → integer ;
// bool → integer{mode:boolean} ; text[] → text{mode:json}. Pas de FK (D5) : les tables
// PowerSync côté client sont plates (relations exprimées par JOIN dans queries.ts). Toute
// colonne SANS `.notNull()` est nullable — y compris les colonnes MASQUÉES par la sync rule
// (D4). Les `.$type<…>()` sont des narrows COMPILE-TIME (non défensifs, cohérent D5/D6).

// --- Tables « SELECT * » : colonnes serveur mirrorées intégralement. --------------------

export const accounts = sqliteTable('accounts', {
  id: text('id').primaryKey(),
  household_id: text('household_id').notNull(),
  name: text('name').notNull(),
  // AccountType = 5 valeurs réelles (backend/modules/accounts/domain.py).
  type: text('type').$type<'courant' | 'livret' | 'epargne' | 'especes' | 'credit'>().notNull(),
  currency: text('currency').notNull(),
  owner_id: text('owner_id'), // nullable (compte commun = pas de propriétaire unique)
  created_at: text('created_at').notNull(),
  archived_at: text('archived_at'), // soft-delete (l'historique reste synchronisé)
})

export const account_members = sqliteTable('account_members', {
  id: text('id').primaryKey(),
  account_id: text('account_id').notNull(),
  user_id: text('user_id').notNull(),
  default_share_ratio: text('default_share_ratio').notNull(), // Decimal(5,4) → text (D3)
  joined_at: text('joined_at').notNull(),
})

export const transactions = sqliteTable('transactions', {
  id: text('id').primaryKey(),
  account_id: text('account_id').notNull(), // dénormalisé (clé de bucket, ADR 0003)
  date: text('date').notNull(), // 'YYYY-MM-DD'
  state: text('state').$type<'draft' | 'planned' | 'confirmed' | 'void'>().notNull(),
  payee: text('payee'),
  description: text('description'),
  category_id: text('category_id'),
  created_by: text('created_by').notNull(),
  created_at: text('created_at').notNull(),
  confirmed_at: text('confirmed_at'),
  voided_at: text('voided_at'),
  tags: text('tags', { mode: 'json' }).$type<string[]>().notNull(), // text[] → JSON
  debt_generation_override: text('debt_generation_override')
    .$type<'default' | 'force_full_debt' | 'force_no_debt'>()
    .notNull(),
  share_request_id: text('share_request_id'),
})

export const splits = sqliteTable('splits', {
  id: text('id').primaryKey(),
  transaction_id: text('transaction_id').notNull(),
  account_id: text('account_id').notNull(), // dénormalisé (ADR 0003)
  category_id: text('category_id'),
  amount_cents: integer('amount_cents').notNull(), // Money (centimes)
  currency: text('currency').notNull(),
  savings_goal_id: text('savings_goal_id'), // colonne dormante (FK inactive côté serveur)
  leg_role: text('leg_role').$type<'funding' | 'classification'>().notNull(), // ADR 0017
})

export const categories = sqliteTable('categories', {
  id: text('id').primaryKey(),
  name: text('name').notNull(),
  color: text('color'),
  icon: text('icon'),
  parent_id: text('parent_id'), // arbre (self-référence, sans FK D5)
  created_at: text('created_at').notNull(),
  archived_at: text('archived_at'),
})

export const budgets = sqliteTable('budgets', {
  id: text('id').primaryKey(),
  category_id: text('category_id').notNull(),
  period_kind: text('period_kind').$type<'monthly' | 'quarterly' | 'yearly'>().notNull(),
  period_start: text('period_start').notNull(), // 'YYYY-MM-DD'
  amount_cents: integer('amount_cents').notNull(),
  currency: text('currency').notNull(),
  scope: text('scope').$type<'personal' | 'shared'>().notNull(),
  created_by: text('created_by').notNull(),
  created_at: text('created_at').notNull(),
  archived_at: text('archived_at'),
  carry_over_remainder: integer('carry_over_remainder', { mode: 'boolean' }).notNull(),
})

export const budget_contributors = sqliteTable('budget_contributors', {
  id: text('id').primaryKey(),
  budget_id: text('budget_id').notNull(),
  user_id: text('user_id').notNull(),
})

export const settlement_lines = sqliteTable('settlement_lines', {
  id: text('id').primaryKey(),
  settlement_id: text('settlement_id').notNull(),
  debt_id: text('debt_id').notNull(),
  amount_cents: integer('amount_cents').notNull(), // > 0 (D-SIGN)
  currency: text('currency').notNull(),
})

// --- Tables à projection MASQUÉE (D4) : colonnes nullable là où la sync rule livre NULL. ---

// Bucket `user_debt`, vue débiteur : `account_id` ET `source_transaction_id` → NULL (D-MASK).
// 10 colonnes exactement — `materialization_trace` est exclu de la publication (D-MAT).
export const debts = sqliteTable('debts', {
  id: text('id').primaryKey(),
  from_user_id: text('from_user_id').notNull(),
  to_user_id: text('to_user_id').notNull(),
  amount_cents: integer('amount_cents').notNull(),
  currency: text('currency').notNull(),
  account_id: text('account_id'), // MASQUÉ côté débiteur → nullable
  source_transaction_id: text('source_transaction_id'), // MASQUÉ côté débiteur → nullable
  origin: text('origin').$type<'shared_account_overflow' | 'personal_share_request'>().notNull(),
  share_ratio: text('share_ratio').notNull(), // Decimal(5,4) → text
  created_at: text('created_at').notNull(),
})

// Bucket `user_debt`, vue débiteur (`requested_from`) : `source_transaction_id` → NULL (D-SR).
// `short_label` est CONSERVÉ (il labellise la REQUÊTE, pas la transaction source).
export const share_requests = sqliteTable('share_requests', {
  id: text('id').primaryKey(),
  source_transaction_id: text('source_transaction_id'), // MASQUÉ côté débiteur → nullable
  requested_by: text('requested_by').notNull(),
  requested_from: text('requested_from').notNull(),
  ratio: text('ratio').notNull(), // Decimal(5,4) → text
  short_label: text('short_label').notNull(),
  created_at: text('created_at').notNull(),
  revoked_at: text('revoked_at'),
})

// Bucket `household` : projection non-PII `SELECT user_id AS id, display_name, role`.
export const users_public = sqliteTable('users_public', {
  id: text('id').primaryKey(), // = user_id (aliasé par la sync rule)
  display_name: text('display_name').notNull(),
  role: text('role').$type<'admin' | 'member'>().notNull(),
})
