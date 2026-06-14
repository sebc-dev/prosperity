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
  test('déconnecté → "offline" (+ lastSyncedAt undefined)', () => {
    const { result } = renderOn(createMockPowerSync()) // connected:false par défaut
    expect(result.current.state).toBe('offline')
    expect(result.current.lastSyncedAt).toBeUndefined()
  })

  test('priorité "offline" : déconnecté MAIS downloading (reconnexion en cours) → "offline"', () => {
    // PowerSync peut publier downloading:true pendant la (re)connexion ; !connected prime.
    // Verrouille l'ordre du ternaire (une inversion ferait basculer en "syncing").
    const mock = createMockPowerSync()
    mock.simulateDataFlow({ downloading: true }) // connected reste false
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('offline')
  })

  test('connecté + dataFlowStatus.downloading → "syncing"', () => {
    const mock = createMockPowerSync()
    mock.simulateReconnect()
    mock.simulateDataFlow({ downloading: true })
    const { result } = renderOn(mock)
    expect(result.current.state).toBe('syncing')
    expect(result.current.lastSyncedAt).toBeUndefined() // pas encore de synchro complète
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
