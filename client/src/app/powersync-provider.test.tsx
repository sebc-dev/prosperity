import { render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { usePowerSync } from '@powersync/react'

import { PowerSyncProvider } from '@/app/powersync-provider'
import { useDrizzle } from '@/lib/drizzle/context'
import { getPowerSync } from '@/lib/powersync/client'
import { createMockPowerSync, type MockPowerSyncDatabase } from '@tests/mocks/powersync'
import type { SQLiteDatabase } from '@/lib/drizzle/types'

// Seam d'injection (§3.6) : pas de point d'injection naturel sur le singleton module-level
// → on substitue client.ts par le `MockPowerSyncDatabase` (aucun wasm/OPFS en jsdom). La
// fabrique est appelée UNE fois dans le module mocké → même instance pour provider ET test.
vi.mock('@/lib/powersync/client', async () => {
  const { createMockPowerSync } = await import('@tests/mocks/powersync')
  const mock = createMockPowerSync()
  const drizzle = { __stub: 'drizzle' } as unknown as SQLiteDatabase
  return { getPowerSync: () => mock, getDrizzle: () => drizzle }
})

// Récupère l'instance mockée partagée (le provider consomme la même via getPowerSync).
const mock = () => getPowerSync() as unknown as MockPowerSyncDatabase

// Sonde : prouve que les deux contextes sont résolus (useDrizzle throw si null).
function Probe() {
  const ps = usePowerSync()
  useDrizzle()
  return <span data-testid="probe">{ps ? 'ok' : 'ko'}</span>
}

let consoleError: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  mock().reset() // le mock est partagé via le module mocké → état neuf à chaque test
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  consoleError.mockRestore()
})

describe('PowerSyncProvider', () => {
  test('monte les deux contextes (PowerSync + Drizzle) sans throw', () => {
    render(
      <PowerSyncProvider>
        <Probe />
      </PowerSyncProvider>,
    )
    expect(screen.getByTestId('probe')).toHaveTextContent('ok')
    expect(consoleError).not.toHaveBeenCalled()
    // connect appelé au montage ; l'instance est connectée.
    expect(mock().connectCount).toBeGreaterThanOrEqual(1)
  })

  test('sous StrictMode : une seule instance, état CONNECTÉ stable en fin de cycle', () => {
    render(
      <StrictMode>
        <PowerSyncProvider>
          <Probe />
        </PowerSyncProvider>
      </StrictMode>,
    )
    const m = mock()
    // StrictMode : connect→disconnect→connect → 2 connect / 1 disconnect, MÊME instance
    // (singleton mocké) → on n'assertе PAS « connect 1× » mais « connecté stable » à la fin.
    expect(m.connectCount).toBe(2)
    expect(m.disconnectCount).toBe(1)
    expect(m.currentStatus.connected).toBe(true)
    expect(screen.getByTestId('probe')).toHaveTextContent('ok')
    expect(consoleError).not.toHaveBeenCalled()
  })
})

// Le Mock est load-bearing pour les phases suivantes : on verrouille ses invariants.
describe('MockPowerSyncDatabase', () => {
  test('connect/disconnect mutent currentStatus.connected', async () => {
    const m = createMockPowerSync()
    expect(m.currentStatus.connected).toBe(false)
    await m.connect()
    expect(m.currentStatus.connected).toBe(true)
    await m.disconnect()
    expect(m.currentStatus.connected).toBe(false)
  })

  test('simulateOffline/Reconnect bascule l’état connecté', () => {
    const m = createMockPowerSync()
    m.simulateReconnect()
    expect(m.currentStatus.connected).toBe(true)
    m.simulateOffline()
    expect(m.currentStatus.connected).toBe(false)
  })

  test('isolation de contexte : deux instances = deux jeux de données disjoints (AC « 2 users »)', () => {
    const userA = createMockPowerSync()
    const userB = createMockPowerSync()
    userA.simulateSyncedFromServer([{ id: 'a1' }])
    userB.simulateSyncedFromServer([{ id: 'b1' }, { id: 'b2' }])
    expect(userA.getSyncedRows()).toEqual([{ id: 'a1' }])
    expect(userB.getSyncedRows()).toEqual([{ id: 'b1' }, { id: 'b2' }])
  })
})
