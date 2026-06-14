import type { AbstractPowerSyncDatabase, PowerSyncBackendConnector } from '@powersync/web'

import { refresh } from '@/lib/auth/session'
import { tokenStore } from '@/lib/auth/token-store'

import { getToken } from './auth-token'
import { uploadData } from './upload'

// Endpoint du service PowerSync (download/sync) — variable PUBLIQUE inlinée dans le bundle
// (jamais de secret). Le write upload, lui, vise le backend FastAPI (`VITE_API_BASE_URL`,
// cf. upload.ts) : deux audiences distinctes pour un même JWT.
//
// Pas de cycle : connector (lib/powersync) → session (lib/auth) → client (lib/api) → schema (leaf) ;
// `session` n'importe RIEN de lib/powersync, et `auth-token` reste leaf (cycle connector↔upload
// toujours cassé).
const ENDPOINT = import.meta.env.VITE_POWERSYNC_URL as string

export const connector: PowerSyncBackendConnector = {
  // Toujours relire un token FRAIS (pas de cache) — contrat SDK. Token absent/expiré (réveil
  // après veille où le timer préemptif n'a pas tiré, ou re-fetch SDK sur 401) → refresh RÉACTIF
  // single-flight AVANT de répondre : tient la promesse héritée « refresh sur 401 en S14.6 » sans
  // boucle (un échec → purge → rejet → login requis ; le SDK propage l'erreur de credentials).
  async fetchCredentials() {
    let token = getToken()
    const exp = tokenStore.get()?.accessExp ?? 0
    if (!token || exp * 1000 <= Date.now()) {
      await refresh()
      token = getToken()
    }
    if (!token) throw new Error('Pas de session — login requis.')
    return { endpoint: ENDPOINT, token }
  },
  uploadData: (db: AbstractPowerSyncDatabase) => uploadData(db),
}
