import { expect, test } from 'vitest'

import config from '../capacitor.config'

// Verrou des valeurs de capacitor.config.ts (automatisable SANS SDK/émulateur, cf. §6.1 stratégie).
// Couvre l'AC « capacitor.config.ts valide » par valeurs (pas seulement « compile »).
test('appId et appName sont définis', () => {
  expect(config.appId).toBe('dev.prosperity.app')
  expect(config.appName).toBeTruthy()
})

test('webDir pointe sur la sortie Vite (verrou de `cap sync`)', () => {
  expect(config.webDir).toBe('dist')
})

test('androidScheme = https (invariant sécurité NET003 : pas de cleartext)', () => {
  expect(config.server?.androidScheme).toBe('https')
})
