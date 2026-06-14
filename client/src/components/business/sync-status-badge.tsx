import { CheckIcon, RefreshCwIcon, WifiOffIcon, type LucideIcon } from 'lucide-react'

import { useSyncStatus, type SyncState } from '@/hooks/use-sync-status'
import { cn } from '@/lib/utils'

// Badge d'état de synchronisation : surface UI de `useSyncStatus` (3 états). `role="status"`
// + `aria-label` → accessible et assertable sans introspection interne.
const META: Record<SyncState, { label: string; Icon: LucideIcon; className: string }> = {
  offline: { label: 'Hors ligne', Icon: WifiOffIcon, className: 'text-muted-foreground' },
  syncing: { label: 'Synchronisation…', Icon: RefreshCwIcon, className: 'text-muted-foreground' },
  synced: { label: 'À jour', Icon: CheckIcon, className: 'text-green-600 dark:text-green-500' },
}

export function SyncStatusBadge() {
  const { state, lastSyncedAt } = useSyncStatus()
  const { label, Icon, className } = META[state]
  // Heure de dernière synchro en infobulle uniquement (pas dans l'aria-label → libellé stable).
  const title =
    state === 'synced' && lastSyncedAt
      ? `Dernière synchro : ${lastSyncedAt.toLocaleTimeString()}`
      : label

  return (
    <span
      role="status"
      aria-label={label}
      title={title}
      className={cn('inline-flex items-center gap-1.5 text-sm', className)}
    >
      <Icon aria-hidden className={cn('size-4', state === 'syncing' && 'animate-spin')} />
      {label}
    </span>
  )
}
