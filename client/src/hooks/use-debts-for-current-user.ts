import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useDrizzle } from '@/lib/drizzle/context'
import { selectDebtsForUser } from '@/lib/drizzle/queries'

// `userId` est passé en paramètre en S14.3 ; le câblage à l'utilisateur courant (via `useAuth`)
// arrive en S14.6. Renvoie les dettes où l'utilisateur est créancier OU débiteur.
export function useDebtsForCurrentUser(userId: string) {
  const db = useDrizzle()
  return useQuery(toCompilableQuery(selectDebtsForUser(db, userId)))
}
