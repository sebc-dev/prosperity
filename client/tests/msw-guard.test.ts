import { expect, test } from 'vitest'

// Verrou PERMANENT d'intégrité du harness : prouve que `onUnhandledRequest: 'error'`
// est actif. Régressable sinon (passage à 'warn'/'bypass', ou `setupFiles` cassé) →
// de futurs tests d'auth/sync pourraient devenir faux-verts en laissant filer un
// appel réseau non mocké. Ne pas retirer.
test('un appel sans handler MSW est rejeté (onUnhandledRequest=error)', async () => {
  // URL absolue (résolue contre l'origine) : garantit que la rejection vient bien de
  // MSW (mode 'error'), et non d'un échec de parsing d'URL relative sous undici.
  const url = new URL('/api/__unhandled__', window.location.origin)
  await expect(fetch(url)).rejects.toThrow()
})
