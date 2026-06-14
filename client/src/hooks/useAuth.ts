import { useSyncExternalStore } from 'react'

import { login, logout, refresh } from '@/lib/auth/session'
import { decodeSub, tokenStore } from '@/lib/auth/token-store'

// Mince adaptateur React au-dessus de `lib/auth/session` : `useSyncExternalStore` dérive
// `isAuthenticated` / `userId` du token-store (source unique, lisible aussi hors-React par
// `getToken`) sans double source de vérité. L'orchestration (login/logout/refresh + auto-refresh)
// vit dans `session.ts` ; ce hook ne fait que ré-exposer ses actions et l'état dérivé.
export function useAuth() {
  const tokens = useSyncExternalStore(tokenStore.subscribe, tokenStore.get)
  return {
    isAuthenticated: tokens !== null,
    userId: tokens ? decodeSub(tokens.accessToken) : null,
    login,
    logout,
    refresh,
  }
}
