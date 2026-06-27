import { toCompilableQuery } from '@powersync/drizzle-driver'
import { useQuery } from '@powersync/react'

import { useAuth } from '@/hooks/useAuth'
import { useDrizzle } from '@/lib/drizzle/context'
import { selectUserById } from '@/lib/drizzle/queries'

// Utilisateur courant (ligne `users_public` synchronisée) dérivé du `userId` du JWT. Sert au
// RBAC d'affichage de la nav (masquer les entrées admin). `db` via `useDrizzle()` (contexte),
// comme tous les hooks data — injectable en test via `<DrizzleContext value={db}>`.
//
// FAIL-SAFE : tant que le rôle n'est pas connu (pas d'`userId`, ou ligne pas encore
// synchronisée), `isAdmin` reste `false` → on ne montre jamais fugitivement une entrée admin.
// Masquage UI ≠ autorisation : l'enforcement réel des écrans admin = S15.9 / backend.
export function useCurrentUser() {
  const { userId } = useAuth()
  const db = useDrizzle()
  // Query TOUJOURS valide : `userId ?? ''` → `where id = ''` → 0 ligne (pas de « requête vide »).
  const { data } = useQuery(toCompilableQuery(selectUserById(db, userId ?? '')))
  const user = data?.[0] ?? null
  return { user, isAdmin: user?.role === 'admin' }
}
