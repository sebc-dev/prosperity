import { PowerSyncContext } from '@powersync/react'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, test } from 'vitest'

import { useSyncStatus } from '@/hooks/use-sync-status'
import {
  asPowerSync,
  createMockPowerSync,
  type MockPowerSyncDatabase,
} from '@tests/mocks/powersync'

// Monte useSyncStatus sur un MockPowerSyncDatabase (le hook lit currentStatus + registerListener).
function renderOn(mock: MockPowerSyncDatabase) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <PowerSyncContext value={asPowerSync(mock)}>{children}</PowerSyncContext>
  )
  return renderHook(() => useSyncStatus(), { wrapper })
}

describe('useSyncStatus', () => {
  test('déconnecté → "offline"', () => {
    const { result } = renderOn(createMockPowerSync()) // connected:false par défaut
    expect(result.current.state).toBe('offline')
  })

  test('connecté + dataFlowStatus.downloading → "syncing"', () => {
    const mock = createMockPowerSync()
    mock.simulateReconnect()
    mock.simulateDataFlow({ downloading: true })
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('syncing')
  })

  test('connecté + uploading → "syncing"', () => {
    const mock = createMockPowerSync()
    mock.simulateReconnect()
    mock.simulateDataFlow({ uploading: true })
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('syncing')
  })

  test('connecté, aucun flux → "synced" (+ lastSyncedAt)', () => {
    const mock = createMockPowerSync()
    mock.simulateReconnect()
    mock.simulateSyncedFromServer([{ id: 'x' }])
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('synced')
    expect(result.current.lastSyncedAt).toBeInstanceOf(Date)
  })

  test('réactif : un changement de statut (registerListener) re-rend le hook', () => {
    const mock = createMockPowerSync()
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('offline')
    act(() => {
      mock.simulateReconnect()
    })
    expect(result.current.state).toBe('synced')
  })
})
