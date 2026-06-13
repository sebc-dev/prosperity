import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useQuery } from '@powersync/react'

import { useDebtsForCurrentUser } from '@/hooks/use-debts-for-current-user'
import { DrizzleContext } from '@/lib/drizzle/context'
import type { SQLiteDatabase } from '@/lib/drizzle/types'

// Test de câblage : useQuery mocké ; on prouve l'appel avec une query compilable + le pass-through.
vi.mock('@powersync/react', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isFetching: false, error: undefined })),
}))

const db = drizzle(new Database(':memory:')) as unknown as SQLiteDatabase
const wrapper = ({ children }: { children: ReactNode }) => (
  <DrizzleContext value={db}>{children}</DrizzleContext>
)

describe('useDebtsForCurrentUser', () => {
  test('appelle useQuery avec une query compilable et expose son résultat', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: [{ id: 'd1' }],
      isLoading: false,
      isFetching: false,
      error: undefined,
    })
    const { result } = renderHook(() => useDebtsForCurrentUser('u1'), { wrapper })

    expect(result.current.data).toEqual([{ id: 'd1' }])
    const compilable = vi.mocked(useQuery).mock.calls[0]?.[0]
    expect(compilable).toHaveProperty('execute')
    expect(compilable).toHaveProperty('compile')
  })
})
