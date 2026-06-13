import { expect, test } from 'vitest'

// Verrou PERMANENT d'intégrité du harness : prouve que `onUnhandledRequest: 'error'`
// est actif. Régressable sinon (passage à 'warn'/'bypass', ou `setupFiles` cassé) →
// de futurs tests d'auth/sync pourraient devenir faux-verts en laissant filer un
// appel réseau non mocké. Ne pas retirer.
test('un appel sans handler MSW est rejeté (onUnhandledRequest=error)', async () => {
  // On assert le MESSAGE de MSW, pas un throw générique : un `.rejects.toThrow()` nu
  // passerait AUSSI en mode 'warn'/'bypass' (rien n'écoutant sur l'origine de test, le
  // fetch échouerait par ECONNREFUSED) → faux-vert. Le message « error strategy » n'est
  // émis QUE par le mode 'error', donc il discrimine réellement la régression visée.
  const url = new URL('/api/__unhandled__', window.location.origin)
  await expect(fetch(url)).rejects.toThrow(/\[MSW\].*error.*strategy/i)
})
