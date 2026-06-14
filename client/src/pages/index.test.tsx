import { screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { renderWithProviders } from '@tests/render'

// __root monte PowerSyncProvider (S14.4) → substitue le singleton par le mock (pas de wasm/OPFS).
vi.mock('@/lib/powersync/client')

test('la route d’accueil affiche le showcase des composants', async () => {
  renderWithProviders(null, { route: '/' })
  // Heading de section stable (couplé au <h1> figé « Composants » du showcase).
  expect(await screen.findByRole('heading', { name: /composants/i })).toBeInTheDocument()
})
