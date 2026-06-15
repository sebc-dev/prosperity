import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useQuery } from '@powersync/react'

import { useCurrentUser } from '@/hooks/use-current-user'
import { DrizzleContext } from '@/lib/drizzle/context'
import type { SQLiteDatabase } from '@/lib/drizzle/types'
import { seedAuth } from '@tests/auth'

// Câblage (gabarit `use-debts-for-current-user.test.tsx`) : `useQuery` mocké → on prouve l'appel
// avec une query compilable + la dérivation `isAdmin`/`user`. `seedAuth()` fournit le `userId`.
vi.mock('@powersync/react', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isFetching: false, error: undefined })),
}))

const db = drizzle(new Database(':memory:')) as unknown as SQLiteDatabase
const wrapper = ({ children }: { children: ReactNode }) => (
  <DrizzleContext value={db}>{children}</DrizzleContext>
)

function mockRow(role: 'admin' | 'member' | null) {
  vi.mocked(useQuery).mockReturnValue({
    data: role ? [{ id: 'u1', display_name: 'Alice', role }] : [],
    isLoading: false,
    isFetching: false,
    error: undefined,
  })
}

describe('useCurrentUser', () => {
  test('admin → isAdmin=true + user exposé ; query compilable', () => {
    seedAuth()
    mockRow('admin')
    const { result } = renderHook(() => useCurrentUser(), { wrapper })
    expect(result.current.isAdmin).toBe(true)
    expect(result.current.user?.display_name).toBe('Alice')
    const compilable = vi.mocked(useQuery).mock.calls[0]?.[0]
    expect(compilable).toHaveProperty('execute')
    expect(compilable).toHaveProperty('compile')
  })

  test('member → isAdmin=false', () => {
    seedAuth()
    mockRow('member')
    const { result } = renderHook(() => useCurrentUser(), { wrapper })
    expect(result.current.isAdmin).toBe(false)
  })

  test('fail-safe : aucune ligne (sync non arrivée) → user=null, isAdmin=false', () => {
    seedAuth()
    mockRow(null)
    const { result } = renderHook(() => useCurrentUser(), { wrapper })
    expect(result.current.user).toBeNull()
    expect(result.current.isAdmin).toBe(false)
  })
})
