import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useQuery } from '@powersync/react'

import { useVisibleAccounts } from '@/hooks/use-visible-accounts'
import { DrizzleContext } from '@/lib/drizzle/context'
import type { SQLiteDatabase } from '@/lib/drizzle/types'

// Test de câblage (D8) : useQuery mocké (la réactivité réelle = S14.4), même patron que
// use-account-balance.test.tsx. Le filtrage SQL lui-même est prouvé dans queries.test.ts (SC-01d).
vi.mock('@powersync/react', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isFetching: false, error: undefined })),
}))

const db = drizzle(new Database(':memory:')) as unknown as SQLiteDatabase
const wrapper = ({ children }: { children: ReactNode }) => (
  <DrizzleContext value={db}>{children}</DrizzleContext>
)

describe('useVisibleAccounts', () => {
  test('SC-01d — câblage : data expose les lignes de comptes (id, name, type, currency) et la requête porte le userId', () => {
    const rows = [
      { id: 'a1', name: 'Compte courant', type: 'courant', currency: 'EUR' },
      { id: 'a2', name: 'Livret', type: 'livret', currency: 'EUR' },
    ]
    vi.mocked(useQuery).mockReturnValue({
      data: rows,
      isLoading: false,
      isFetching: false,
      error: undefined,
    })

    const { result } = renderHook(() => useVisibleAccounts('u1'), { wrapper })

    expect(result.current.data).toEqual(rows)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeUndefined()
    // Le userId passé au hook arrive bien dans les paramètres SQL de la requête compilée
    // (`selectVisibleAccounts(db, userId)` → `toCompilableQuery`), pas une requête figée.
    const query = vi.mocked(useQuery).mock.lastCall?.[0]
    if (typeof query !== 'object' || query === null || !('compile' in query)) {
      throw new Error('useQuery doit recevoir une CompilableQuery')
    }
    const compiled = query.compile()
    expect(compiled.parameters).toContain('u1')
    expect(compiled.sql).toMatch(/from "accounts"/i)
  })

  test('data vide (ex. chargement) → tableau vide, isLoading propagé', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: [],
      isLoading: true,
      isFetching: true,
      error: undefined,
    })

    const { result } = renderHook(() => useVisibleAccounts('u1'), { wrapper })

    expect(result.current.data).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })
})
