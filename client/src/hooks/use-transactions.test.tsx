import Database from 'better-sqlite3'
import { drizzle } from 'drizzle-orm/better-sqlite3'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useQuery } from '@powersync/react'

import { useTransactions } from '@/hooks/use-transactions'
import { DrizzleContext, useDrizzle } from '@/lib/drizzle/context'
import type { SQLiteDatabase } from '@/lib/drizzle/types'

// Test de CÂBLAGE/CONTRAT (pas de réactivité — celle-ci est portée par queries.test.ts).
// On mocke `useQuery` : ce qui re-render est piloté par le mock, pas par un watch local.
// `toCompilableQuery` n'est PAS exercé (intégration réelle = S14.4).
vi.mock('@powersync/react', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isFetching: false, error: undefined })),
}))

// db Drizzle réelle (better-sqlite3) pour que selectTransactions construise une vraie query ;
// aucune exécution n'a lieu (useQuery est mocké) → pas besoin d'appliquer le DDL.
const db = drizzle(new Database(':memory:')) as unknown as SQLiteDatabase
const wrapper = ({ children }: { children: ReactNode }) => (
  <DrizzleContext value={db}>{children}</DrizzleContext>
)

describe('useTransactions (câblage)', () => {
  test('appelle useQuery avec une query compilable et expose son résultat', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: [{ id: 't1' }],
      isLoading: false,
      isFetching: false,
      error: undefined,
    })

    const { result } = renderHook(() => useTransactions({ accountId: 'a1' }), { wrapper })

    expect(result.current.data).toEqual([{ id: 't1' }])
    // useQuery reçoit une CompilableQuery (execute + compile), pas la query Drizzle brute.
    const compilable = vi.mocked(useQuery).mock.calls[0]?.[0]
    expect(compilable).toHaveProperty('execute')
    expect(compilable).toHaveProperty('compile')
  })

  test('useDrizzle throw hors provider (échec sûr, gabarit useTheme)', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    expect(() => renderHook(() => useDrizzle())).toThrow(/Drizzle/)
    spy.mockRestore()
  })
})
