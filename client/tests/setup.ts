import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './msw/server'

// MSW intercepte au niveau RÉSEAU. `onUnhandledRequest: 'error'` fait échouer tout
// appel non mocké (anti faux-vert, cf. tests/msw-guard.test.ts).
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  cleanup() // démonte les composants Testing Library
  server.resetHandlers() // purge les handlers ad-hoc (anti-fuite d'état inter-tests)
})
afterAll(() => {
  server.close()
})
