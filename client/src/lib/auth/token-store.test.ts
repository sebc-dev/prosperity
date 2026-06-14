// @vitest-environment jsdom
import { afterEach, describe, expect, test, vi } from 'vitest'

import { decodeExp, decodeSub, tokenStore, type AuthTokens } from '@/lib/auth/token-store'
import { makeTestJwt } from '@tests/auth'

const SAMPLE: AuthTokens = { accessToken: 'a.b.c', refreshToken: 'rt', accessExp: 123 }

afterEach(() => {
  tokenStore.set(null) // l'afterEach global le fait aussi, mais on isole ce fichier
})

describe('tokenStore', () => {
  test('set/get aller-retour ; getAccessToken reflète le dernier set SYNCHRONIQUEMENT', () => {
    expect(tokenStore.get()).toBeNull()
    tokenStore.set(SAMPLE)
    expect(tokenStore.get()).toEqual(SAMPLE)
    expect(tokenStore.getAccessToken()).toBe('a.b.c')
  })

  test('set(null) purge', () => {
    tokenStore.set(SAMPLE)
    tokenStore.set(null)
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getAccessToken()).toBeNull()
  })

  test('subscribe notifie sur set ; l’unsubscribe coupe les notifications', () => {
    const l = vi.fn()
    const unsub = tokenStore.subscribe(l)
    tokenStore.set(SAMPLE)
    expect(l).toHaveBeenCalledTimes(1)
    unsub()
    tokenStore.set(null)
    expect(l).toHaveBeenCalledTimes(1) // plus de notification après unsubscribe
  })
})

describe('decodeExp / decodeSub', () => {
  test('JWT valide → exp et sub extraits', () => {
    const jwt = makeTestJwt({ sub: 'user-42', exp: 1_700_000_000 })
    expect(decodeExp(jwt)).toBe(1_700_000_000)
    expect(decodeSub(jwt)).toBe('user-42')
  })

  test('base64url avec - / _ décodé correctement (normalisation -_ → +/)', () => {
    // `sub: 'a?b>c'` produit un segment payload contenant un `-` (base64url) que `atob`
    // (base64 strict) rejetterait sans la normalisation : preuve qu'elle est bien appliquée.
    const sub = 'a?b>c'
    const jwt = makeTestJwt({ sub, exp: 42 })
    expect(jwt.split('.')[1]).toMatch(/[-_]/) // garde-fou : le segment exerce bien le cas
    expect(decodeSub(jwt)).toBe(sub)
    expect(decodeExp(jwt)).toBe(42)
  })

  test('token malformé (pas 3 segments) → null', () => {
    expect(decodeExp('not-a-jwt')).toBeNull()
    expect(decodeSub('not-a-jwt')).toBeNull()
  })

  test('base64 invalide dans le payload → null (pas de crash)', () => {
    expect(decodeExp('h.@@@.s')).toBeNull()
    expect(decodeSub('h.@@@.s')).toBeNull()
  })

  test('payload sans exp / sans sub → null', () => {
    const noExp = `h.${btoa(JSON.stringify({ sub: 'x' })).replace(/=+$/, '')}.s`
    const noSub = `h.${btoa(JSON.stringify({ exp: 1 })).replace(/=+$/, '')}.s`
    expect(decodeExp(noExp)).toBeNull()
    expect(decodeSub(noSub)).toBeNull()
  })
})
