import type { AbstractPowerSyncDatabase, PowerSyncBackendConnector } from '@powersync/web'

import { getToken } from './auth-token'
import { uploadData } from './upload'

// Endpoint du service PowerSync (download/sync) — variable PUBLIQUE inlinée dans le bundle
// (jamais de secret). Le write upload, lui, vise le backend FastAPI (`VITE_API_BASE_URL`,
// cf. upload.ts) : deux audiences distinctes pour un même JWT.
const ENDPOINT = import.meta.env.VITE_POWERSYNC_URL as string

export const connector: PowerSyncBackendConnector = {
  // Toujours relire un token FRAIS (pas de cache) — contrat SDK. En S14.4 c'est le même
  // localStorage statique (refresh réel = S14.6). Pas de session → rejet (login requis) ;
  // le SDK propage l'erreur comme tout échec de credentials.
  fetchCredentials() {
    const token = getToken()
    if (!token) return Promise.reject(new Error('Pas de session — login requis (S14.6).'))
    return Promise.resolve({ endpoint: ENDPOINT, token })
  },
  uploadData: (db: AbstractPowerSyncDatabase) => uploadData(db),
}
