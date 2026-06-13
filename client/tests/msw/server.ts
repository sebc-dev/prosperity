import { setupServer } from 'msw/node'

import { handlers } from './handlers'

// Serveur MSW Node (pas de worker navigateur : aucun `mockServiceWorker.js` embarqué
// en prod). Utilisé par tous les tests Vitest via tests/setup.ts.
export const server = setupServer(...handlers)
