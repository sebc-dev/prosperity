import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SyncStatusBadge } from '@/components/business/sync-status-badge'
import { useSyncStatus, type SyncState } from '@/hooks/use-sync-status'

// On isole le badge de PowerSync : useSyncStatus mocké → on teste le MAPPING état→libellé
// (via role/aria-label, sans introspection interne).
vi.mock('@/hooks/use-sync-status', () => ({ useSyncStatus: vi.fn() }))
const mockHook = vi.mocked(useSyncStatus)

function setState(state: SyncState, lastSyncedAt?: Date) {
  mockHook.mockReturnValue({ state, lastSyncedAt })
}

beforeEach(() => {
  mockHook.mockReset()
})

describe('SyncStatusBadge', () => {
  test('offline → libellé "Hors ligne"', () => {
    setState('offline')
    render(<SyncStatusBadge />)
    expect(screen.getByRole('status', { name: 'Hors ligne' })).toHaveTextContent('Hors ligne')
  })

  test('syncing → libellé "Synchronisation…"', () => {
    setState('syncing')
    render(<SyncStatusBadge />)
    expect(screen.getByRole('status', { name: 'Synchronisation…' })).toHaveTextContent(
      'Synchronisation…',
    )
  })

  test('synced → libellé "À jour"', () => {
    setState('synced', new Date(0))
    render(<SyncStatusBadge />)
    expect(screen.getByRole('status', { name: 'À jour' })).toHaveTextContent('À jour')
  })
})
