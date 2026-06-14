import { SecureStorage } from '@aparajita/capacitor-secure-storage'

import type { StorageBackend } from './types'

// Backend natif : Secure Storage adossé au Keystore (Android) / Keychain (iOS) — résout
// capacitor-security STO006/STO002 (le JWT ne vit plus en localStorage sur mobile). Le plugin
// `@aparajita/capacitor-secure-storage` (Cap 8) est Cap-8-ready → chemin nominal, pas de stub
// (la contingence fail-closed de l'encadré D3 n'a pas eu lieu d'être).
//
// `SecureStorage.get` renvoie `DataType | null` ; on borne à `string | null` (le wrapper ne
// stocke que des strings ; une valeur corrompue/non-string → null). Les rejets du plugin
// (Keystore verrouillé, clé corrompue) sont PROPAGÉS (contrat consommé par S14.6).
export const nativeBackend: StorageBackend = {
  async get(key) {
    const value = await SecureStorage.get(key)
    return typeof value === 'string' ? value : null
  },
  set: (key, value) => SecureStorage.set(key, value), // le plugin renvoie déjà Promise<void>
  remove: (key) => SecureStorage.remove(key).then(() => undefined), // plugin: Promise<boolean> → void
}
