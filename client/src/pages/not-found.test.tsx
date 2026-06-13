import { screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { renderWithProviders } from '@tests/render'

test('une route inconnue rend le 404 (notFoundComponent)', async () => {
  renderWithProviders(null, { route: '/route-inexistante' })
  expect(await screen.findByText(/introuvable|not found/i)).toBeInTheDocument()
})
