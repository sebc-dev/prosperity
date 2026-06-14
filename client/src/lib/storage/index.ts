import { Capacitor } from '@capacitor/core'

import { nativeBackend } from './native'
import { webBackend } from './web'
import type { StorageBackend } from './types'

export { STORAGE_KEYS } from './types'
export type { StorageBackend } from './types'

// Routage PAR APPEL (D2) — `Capacitor.isNativePlatform()` (pas de sniffing UA), évalué à chaque
// appel et non figé au load → les deux branches restent testables sans `resetModules`.
const backend = (): StorageBackend => (Capacitor.isNativePlatform() ? nativeBackend : webBackend)

// API de stockage UNIQUE, async : Secure Storage sur natif, localStorage sur web. Source unique
// pour le JWT (consommé en S14.6, D5) et toute autre donnée sensible côté client.
export const storage: StorageBackend = {
  get: (key) => backend().get(key),
  set: (key, value) => backend().set(key, value),
  remove: (key) => backend().remove(key),
}
