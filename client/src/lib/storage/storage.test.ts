import { Capacitor } from '@capacitor/core'
import { SecureStorage } from '@aparajita/capacitor-secure-storage'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { storage, STORAGE_KEYS } from '@/lib/storage'

// Mocks explicites : isNativePlatform re-piloté par test ; le plugin Secure Storage mocké (jamais
// le vrai Keystore en jsdom). Le backend web utilise le localStorage RÉEL de jsdom.
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: vi.fn() } }))
vi.mock('@aparajita/capacitor-secure-storage', () => ({
  SecureStorage: { get: vi.fn(), set: vi.fn(), remove: vi.fn() },
}))

const isNative = vi.mocked(Capacitor.isNativePlatform)
const plugin = vi.mocked(SecureStorage)

// Chemin nominal : le plugin réel (Cap-8-ready) est utilisé → la délégation au plugin EST testée
// (pas de stub). Si un jour le stub fail-closed de l'encadré D3 est requis, passer ce drapeau à
// true isolerait le bloc « délégation au plugin » sans toucher aux tests d'interface.
const PLUGIN_STUBBED = false

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(() => {
  // localStorage réel (jsdom) purgé par tests/setup.ts ; on restaure les spies ad-hoc.
  vi.restoreAllMocks()
})

// --- Contrat de l'interface StorageBackend (survit aux régimes nominal/stub) ----------------

describe('storage — branche web (localStorage)', () => {
  beforeEach(() => isNative.mockReturnValue(false))

  test('set → get round-trip via localStorage, sans appeler le plugin natif', async () => {
    await storage.set('k', 'v')
    expect(await storage.get('k')).toBe('v')
    expect(localStorage.getItem('k')).toBe('v')
    expect(plugin.set).not.toHaveBeenCalled()
    expect(plugin.get).not.toHaveBeenCalled()
  })

  test('get clé absente → null', async () => {
    expect(await storage.get('absente')).toBeNull()
  })

  test('remove efface (get → null ensuite)', async () => {
    await storage.set('k', 'v')
    await storage.remove('k')
    expect(await storage.get('k')).toBeNull()
  })
})

describe.skipIf(PLUGIN_STUBBED)('storage — branche native (Secure Storage)', () => {
  beforeEach(() => {
    isNative.mockReturnValue(true)
    plugin.set.mockResolvedValue(undefined)
    plugin.remove.mockResolvedValue(true) // le plugin renvoie Promise<boolean>
  })

  test('set/get/remove délèguent au plugin (Keystore), sans toucher localStorage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    plugin.get.mockResolvedValue('depuis-keystore')

    await storage.set('k', 'v')
    expect(plugin.set).toHaveBeenCalledWith('k', 'v')
    expect(await storage.get('k')).toBe('depuis-keystore')
    expect(plugin.get).toHaveBeenCalledWith('k')
    await storage.remove('k')
    expect(plugin.remove).toHaveBeenCalledWith('k')

    expect(setItem).not.toHaveBeenCalled() // localStorage JAMAIS touché sur natif
  })

  test('valeur non-string du plugin (corrompue) → null (borne string|null)', async () => {
    plugin.get.mockResolvedValue(42) // DataType non-string
    expect(await storage.get('k')).toBeNull()
  })

  test('rejet du plugin (Keystore verrouillé) PROPAGÉ (pas de swallow)', async () => {
    plugin.get.mockRejectedValue(new Error('keystore locked'))
    await expect(storage.get('k')).rejects.toThrow('keystore locked')
  })
})

describe('storage — routage par appel (D2)', () => {
  test('isNativePlatform basculé entre deux appels → cible l’autre backend', async () => {
    plugin.get.mockResolvedValue('natif')
    // 1er appel : natif → plugin ; 2e appel : web → localStorage.
    isNative.mockReturnValueOnce(true).mockReturnValueOnce(false)
    expect(await storage.get('k')).toBe('natif') // plugin
    localStorage.setItem('k', 'web')
    expect(await storage.get('k')).toBe('web') // localStorage
  })
})

describe('storage — cohérence web/natif sur la valeur vide ""', () => {
  test('web : une valeur "" stockée est rendue "" (pas null)', async () => {
    isNative.mockReturnValue(false)
    await storage.set('k', '')
    expect(await storage.get('k')).toBe('')
  })

  test('natif : une valeur "" rendue par le plugin reste "" (pas null)', async () => {
    isNative.mockReturnValue(true)
    plugin.get.mockResolvedValue('')
    expect(await storage.get('k')).toBe('')
  })
})

test('STORAGE_KEYS.jwt stable', () => {
  // Verrou de stabilité de la constante (PAS un anti-drift complet : auth-token.ts n'importe pas
  // encore STORAGE_KEYS — rewiring du consommateur différé en S14.6, D5).
  expect(STORAGE_KEYS.jwt).toBe('prosperity-jwt')
})
