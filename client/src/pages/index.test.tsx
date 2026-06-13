import { screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { renderWithProviders } from '@tests/render'

test('la route d’accueil affiche Hello', async () => {
  renderWithProviders(null, { route: '/' })
  expect(await screen.findByRole('heading', { name: /hello/i })).toBeInTheDocument()
})
