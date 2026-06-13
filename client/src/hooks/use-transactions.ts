import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useDrizzle } from '@/lib/drizzle/context'
import { selectTransactions, type TransactionFilters } from '@/lib/drizzle/queries'

// `useQuery` ré-évalue automatiquement quand les tables touchées changent (watch PowerSync,
// câblé en S14.4). En S14.3 le hook est testé en câblage (useQuery stubé).
export function useTransactions(filters: TransactionFilters = {}) {
  const db = useDrizzle()
  return useQuery(toCompilableQuery(selectTransactions(db, filters)))
}
