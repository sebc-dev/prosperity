import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { expect, test } from 'vitest'

import { server } from '@tests/msw/server'
import { renderWithProviders } from '@tests/render'

import { HealthProbe } from './health'

test('un appel réseau est intercepté par MSW (niveau réseau, pas de mock fetch)', async () => {
  server.use(http.get('/api/health', () => HttpResponse.json({ status: 'ok' })))
  renderWithProviders(<HealthProbe />)
  expect(await screen.findByText(/ok/i)).toBeInTheDocument()
})
