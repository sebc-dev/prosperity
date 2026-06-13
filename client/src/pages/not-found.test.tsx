import { screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// __root monte PowerSyncProvider (S14.4) → substitue le singleton par le mock (pas de wasm/OPFS).
vi.mock('@/lib/powersync/client')

test('une route inconnue rend le 404 (notFoundComponent)', async () => {
  renderWithProviders(null, { route: '/route-inexistante' })
  expect(await screen.findByText(/introuvable|not found/i)).toBeInTheDocument()
})
