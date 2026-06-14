// Contrat commun aux deux backends (web localStorage / natif Secure Storage). ASYNC (D1) :
// le Secure Storage natif (Keystore/Keychain) est Promise-only → l'API unique l'est aussi.
export interface StorageBackend {
  get(key: string): Promise<string | null>
  set(key: string, value: string): Promise<void>
  remove(key: string): Promise<void>
}

// Clés connues (source unique, évite les littéraux dispersés). `jwt` = access token (consommé en
// S14.6 par `lib/auth/session`, hydraté au boot). `refreshToken` = refresh opaque (rotation, TTL
// 30 j) : persisté pour réutiliser l'access caché hors-ligne au cold start sans round-trip.
export const STORAGE_KEYS = {
  jwt: 'prosperity-jwt',
  refreshToken: 'prosperity-refresh',
} as const
