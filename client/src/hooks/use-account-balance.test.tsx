import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useQuery } from '@powersync/react'

import { useAccountBalance } from '@/hooks/use-account-balance'
import { DrizzleContext } from '@/lib/drizzle/context'
import type { SQLiteDatabase } from '@/lib/drizzle/types'

// Test de câblage + unwrap (D8) : useQuery mocké (la réactivité réelle = S14.4).
vi.mock('@powersync/react', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isFetching: false, error: undefined })),
}))

const db = drizzle(new Database(':memory:')) as unknown as SQLiteDatabase
const wrapper = ({ children }: { children: ReactNode }) => (
  <DrizzleContext value={db}>{children}</DrizzleContext>
)

describe('useAccountBalance', () => {
  test('unwrap l’agrégat scalaire → balanceCents', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: [{ balanceCents: 4200 }],
      isLoading: false,
      isFetching: false,
      error: undefined,
    })
    const { result } = renderHook(() => useAccountBalance('a1'), { wrapper })
    expect(result.current.balanceCents).toBe(4200)
  })

  test('data vide (ex. chargement) → balanceCents 0 (branche ?? 0)', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: [],
      isLoading: true,
      isFetching: true,
      error: undefined,
    })
    const { result } = renderHook(() => useAccountBalance('a1'), { wrapper })
    expect(result.current.balanceCents).toBe(0)
  })
})
