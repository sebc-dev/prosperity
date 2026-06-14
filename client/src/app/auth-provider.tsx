import { useEffect, useState, type ReactNode } from 'react'

import { hydrateSession } from '@/lib/auth/session'

// Hydrate le token-store (storage → mémoire) AVANT de monter ses enfants. Monté AU-DESSUS du
// `RouterProvider` (dans `main.tsx`) : tant que `ready === false` il rend `null`, donc le routeur
// — et tout `beforeLoad` (garde d'auth) ainsi que PowerSyncProvider — n'est monté qu'APRÈS
// l'hydratation. La lecture SYNC `getToken()` de la garde est ainsi fiable au cold start, et
// PowerSync ne se connecte jamais avec un token absent : la fenêtre de course au boot est éliminée.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    void hydrateSession().finally(() => {
      setReady(true)
    })
  }, [])
  if (!ready) return null // bref état neutre, avant le 1er render du routeur (pas de flash login)
  return <>{children}</>
}
