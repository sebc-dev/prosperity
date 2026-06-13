import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useDrizzle } from '@/lib/drizzle/context'
import { selectAccountBalance } from '@/lib/drizzle/queries'

// Renvoie le solde réel (centimes) du compte ; unwrap l'agrégat scalaire (D8) → 0 par défaut.
export function useAccountBalance(accountId: string) {
  const db = useDrizzle()
  const result = useQuery(toCompilableQuery(selectAccountBalance(db, accountId)))
  return { ...result, balanceCents: result.data[0]?.balanceCents ?? 0 }
}
