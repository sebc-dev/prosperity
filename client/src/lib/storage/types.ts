// Contrat commun aux deux backends (web localStorage / natif Secure Storage). ASYNC (D1) :
// le Secure Storage natif (Keystore/Keychain) est Promise-only → l'API unique l'est aussi.
export interface StorageBackend {
  get(key: string): Promise<string | null>
  set(key: string, value: string): Promise<void>
  remove(key: string): Promise<void>
}

// Clés connues (source unique, évite les littéraux dispersés). Le JWT est CONSOMMÉ en S14.6
// (rewiring de auth-token.ts différé, D5) ; déclaré ici pour que le wrapper soit la place
// documentée des clés sensibles.
export const STORAGE_KEYS = { jwt: 'prosperity-jwt' } as const
