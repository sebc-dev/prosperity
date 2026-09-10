import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useDrizzle } from '@/lib/drizzle/context'
import { selectVisibleAccounts } from '@/lib/drizzle/queries'

// Comptes visibles par le membre courant (perso + commun, hors archivés) — cf. `selectVisibleAccounts`.
// Ne porte PAS le solde (réutilisation de `useAccountBalance` par ligne, cf. `BalancePanel`).
export function useVisibleAccounts(userId: string) {
  const db = useDrizzle()
  return useQuery(toCompilableQuery(selectVisibleAccounts(db, userId)))
}
