import { screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { renderWithProviders } from '@tests/render'

test('la route d’accueil affiche le showcase des composants', async () => {
  renderWithProviders(null, { route: '/' })
  // Heading de section stable (couplé au <h1> figé « Composants » du showcase).
  expect(await screen.findByRole('heading', { name: /composants/i })).toBeInTheDocument()
})
