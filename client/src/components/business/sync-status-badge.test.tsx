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

  test('synced → libellé "À jour" (+ title = heure de dernière synchro)', () => {
    const at = new Date(0)
    setState('synced', at)
    render(<SyncStatusBadge />)
    const badge = screen.getByRole('status', { name: 'À jour' })
    expect(badge).toHaveTextContent('À jour')
    // title porte l'horodatage (assertion sur la présence du préfixe, pas l'heure locale exacte).
    expect(badge).toHaveAttribute('title', expect.stringContaining('Dernière synchro'))
  })

  test('synced SANS lastSyncedAt (avant 1ʳᵉ synchro) → title retombe sur le libellé', () => {
    setState('synced', undefined)
    render(<SyncStatusBadge />)
    const badge = screen.getByRole('status', { name: 'À jour' })
    expect(badge).toHaveTextContent('À jour')
    expect(badge).toHaveAttribute('title', 'À jour') // branche title=label
  })
})
