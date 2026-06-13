import { useStatus } from '@powersync/react'

// État de synchronisation dérivé du `SyncStatus` PowerSync (D10), réduit à 3 états pour l'UI.
export type SyncState = 'offline' | 'syncing' | 'synced'

export function useSyncStatus(): { state: SyncState; lastSyncedAt: Date | undefined } {
  const s = useStatus()
  // ⚠️ `downloading`/`uploading` vivent SOUS `dataFlowStatus` (getter), pas en racine —
  // sinon l'état 'syncing' ne serait jamais atteint (toujours 'synced' dès connecté).
  const { downloading, uploading } = s.dataFlowStatus
  const state: SyncState = !s.connected
    ? 'offline'
    : downloading || uploading
      ? 'syncing'
      : 'synced'
  return { state, lastSyncedAt: s.lastSyncedAt }
}
