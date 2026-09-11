import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useDrizzle } from '@/lib/drizzle/context'
import { selectNetDebtsByCounterparty } from '@/lib/drizzle/queries'

// Dette nette par contrepartie (SC-02a) — délègue l'agrégation (SQL, signe, `HAVING != 0`) à la
// query factory ; le hook ne fait que la câbler à `useQuery`, même patron que `useAccountBalance` /
// `useDebtsForCurrentUser`.
export function useDebtSummary(userId: string) {
  const db = useDrizzle()
  return useQuery(toCompilableQuery(selectNetDebtsByCounterparty(db, userId)))
}
