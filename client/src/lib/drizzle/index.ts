// Surface publique du schéma local : ré-exporte les tables + les types `$inferSelect`
// réutilisables par l'UI (pas de redéclaration des shapes côté composants — note issue #207).
export * from './schema'

import type {
  account_members,
  accounts,
  budget_contributors,
  budgets,
  categories,
  debts,
  settlement_lines,
  share_requests,
  splits,
  transactions,
  users_public,
} from './schema'

export type Account = typeof accounts.$inferSelect
export type AccountMember = typeof account_members.$inferSelect
export type Transaction = typeof transactions.$inferSelect
export type Split = typeof splits.$inferSelect
export type Category = typeof categories.$inferSelect
export type Budget = typeof budgets.$inferSelect
export type BudgetContributor = typeof budget_contributors.$inferSelect
// account_id / source_transaction_id : `string | null` (masquage débiteur, D4).
export type Debt = typeof debts.$inferSelect
export type ShareRequest = typeof share_requests.$inferSelect
export type SettlementLine = typeof settlement_lines.$inferSelect
export type UserPublic = typeof users_public.$inferSelect
