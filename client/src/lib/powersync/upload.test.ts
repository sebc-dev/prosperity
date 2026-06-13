// @vitest-environment jsdom
import { UpdateType } from '@powersync/web'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { v5 as uuidv5 } from 'uuid'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { setAdoptSink, type AdoptedId } from '@/lib/powersync/adopt'
import type { BatchUpload, WriteResult } from '@/lib/powersync/protocol'
import { NS, uploadData } from '@/lib/powersync/upload'
import { asPowerSync, createMockPowerSync, crudEntry } from '@tests/mocks/powersync'
import { server } from '@tests/msw/server'

// Toast mocké : on n'assertе que les MESSAGES (mappés FR), jamais l'UI Sonner réelle.
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))
const toastError = vi.mocked(toast.error)

const API = 'http://localhost:8000'
const ENDPOINT = `${API}/sync/upload`

// Fixtures CrudEntry réalistes (op/opData/id/clientId).
const PUT_ACC = crudEntry({
  clientId: 1,
  op: UpdateType.PUT,
  table: 'accounts',
  id: 'local-acc-1',
  opData: { name: 'Courant', type: 'courant', currency: 'EUR', household_id: 'h1' },
})
const PATCH_TX = crudEntry({
  clientId: 2,
  op: UpdateType.PATCH,
  table: 'transactions',
  id: 'tx-1',
  opData: { payee: 'Carrefour' },
})
const DEL_SPLIT = crudEntry({ clientId: 3, op: UpdateType.DELETE, table: 'splits', id: 'sp-1' })

const rid = (clientId: number) => uuidv5(String(clientId), NS)

interface Captured {
  body: BatchUpload
  auth: string | null
}

/** Installe un handler MSW pour POST /sync/upload et capture chaque requête reçue. */
function interceptUpload(respond: (call: number) => Response | Promise<Response>) {
  const captured: Captured[] = []
  server.use(
    http.post(ENDPOINT, async ({ request }) => {
      captured.push({
        body: (await request.json()) as BatchUpload,
        auth: request.headers.get('authorization'),
      })
      return respond(captured.length)
    }),
  )
  return captured
}

const ok = (client_request_id: string, server_values?: Record<string, unknown>): WriteResult => ({
  client_request_id,
  success: true,
  server_values: server_values ?? null,
})

beforeEach(() => {
  vi.stubEnv('VITE_API_BASE_URL', API)
  localStorage.setItem('prosperity-jwt', 'tok')
  toastError.mockClear()
})
afterEach(() => {
  vi.unstubAllEnvs()
  localStorage.clear()
  setAdoptSink(() => {})
})

describe('uploadData — mapping CrudEntry→Mutation', () => {
  test('PUT→insert (sans id), PATCH/DELETE→{id,…}, client_request_id = uuidv5(clientId, NS)', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC, PATCH_TX, DEL_SPLIT])
    const captured = interceptUpload(() => HttpResponse.json([ok(rid(1)), ok(rid(2)), ok(rid(3))]))

    await uploadData(asPowerSync(db))

    const { mutations } = captured[0]!.body
    // insert : payload SANS id (id généré serveur).
    expect(mutations[0]).toEqual({
      client_request_id: rid(1),
      table: 'accounts',
      op: 'insert',
      payload: { name: 'Courant', type: 'courant', currency: 'EUR', household_id: 'h1' },
    })
    expect(mutations[0]!.payload).not.toHaveProperty('id')
    // update : payload AVEC id.
    expect(mutations[1]).toEqual({
      client_request_id: rid(2),
      table: 'transactions',
      op: 'update',
      payload: { id: 'tx-1', payee: 'Carrefour' },
    })
    // delete : payload = { id } (opData absent).
    expect(mutations[2]).toEqual({
      client_request_id: rid(3),
      table: 'splits',
      op: 'delete',
      payload: { id: 'sp-1' },
    })
  })

  test('le client_request_id est STABLE pour la même CrudEntry (idempotence)', () => {
    expect(rid(1)).toBe(uuidv5('1', NS))
    expect(rid(1)).toBe(rid(1))
  })
})

describe('uploadData — 200 (succès / erreurs typées)', () => {
  test('tous succès : complete() (purge), 0 toast, server_values capturé (sink observable)', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    const adopted: AdoptedId[] = []
    setAdoptSink((e) => adopted.push(e))
    interceptUpload(() => HttpResponse.json([ok(rid(1), { id: 'srv-acc-1' })]))

    await uploadData(asPowerSync(db))

    expect(db.hasPendingCrud).toBe(false) // batch purgé
    expect(toastError).not.toHaveBeenCalled()
    expect(adopted).toEqual([{ table: 'accounts', localId: 'local-acc-1', serverId: 'srv-acc-1' }])
  })

  test('erreurs typées multiples (codes distincts) : N toasts MAPPÉS distincts, complete() une fois', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC, PATCH_TX])
    interceptUpload(() =>
      HttpResponse.json([
        {
          client_request_id: rid(1),
          success: false,
          error: { code: 'validation_error', message: 'col x' },
        },
        {
          client_request_id: rid(2),
          success: false,
          error: { code: 'unbalanced_transaction', message: 'sum≠0' },
        },
      ]),
    )

    await uploadData(asPowerSync(db))

    expect(toastError).toHaveBeenCalledTimes(2)
    expect(toastError).toHaveBeenCalledWith('Données invalides.')
    expect(toastError).toHaveBeenCalledWith('La transaction n’est pas équilibrée.')
    expect(db.hasPendingCrud).toBe(false)
  })

  test('anti-fuite : un error.message serveur exotique n’apparaît JAMAIS dans le toast', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    interceptUpload(() =>
      HttpResponse.json([
        {
          client_request_id: rid(1),
          success: false,
          error: { code: 'auth_denied', message: 'STACKTRACE secret /var/secret 0xDEAD' },
        },
      ]),
    )

    await uploadData(asPowerSync(db))

    expect(toastError).toHaveBeenCalledTimes(1)
    expect(toastError).toHaveBeenCalledWith('Action non autorisée.')
    expect(toastError).not.toHaveBeenCalledWith(expect.stringContaining('secret'))
  })

  test('corrélation par id : WriteResult[] DÉSORDONNÉ → adoption jointe à la bonne CrudEntry', async () => {
    const ins1 = crudEntry({ clientId: 10, op: UpdateType.PUT, table: 'accounts', id: 'loc-10' })
    const ins2 = crudEntry({
      clientId: 20,
      op: UpdateType.PUT,
      table: 'transactions',
      id: 'loc-20',
    })
    const db = createMockPowerSync()
    db.enqueueCrud([ins1, ins2])
    const adopted: AdoptedId[] = []
    setAdoptSink((e) => adopted.push(e))
    // Réponses dans l'ORDRE INVERSE des mutations.
    interceptUpload(() =>
      HttpResponse.json([ok(rid(20), { id: 'srv-20' }), ok(rid(10), { id: 'srv-10' })]),
    )

    await uploadData(asPowerSync(db))

    expect(adopted).toContainEqual({ table: 'accounts', localId: 'loc-10', serverId: 'srv-10' })
    expect(adopted).toContainEqual({ table: 'transactions', localId: 'loc-20', serverId: 'srv-20' })
  })
})

describe('uploadData — classification HTTP (purge vs retry)', () => {
  test('422 : toast(GENERIC) + complete() (purge, PAS de retry) + console.error dev SANS payload', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    interceptUpload(() => new HttpResponse(null, { status: 422 }))

    await expect(uploadData(asPowerSync(db))).resolves.toBeUndefined() // pas de throw

    expect(toastError).toHaveBeenCalledWith('Une erreur est survenue.')
    expect(db.hasPendingCrud).toBe(false) // PURGÉ (anti boucle infinie)
    // Diagnostic dev : status + ids + count, mais JAMAIS le payload (PII).
    expect(consoleError).toHaveBeenCalledWith('[powersync] rejet de forme — purge', {
      status: 422,
      client_request_ids: [rid(1)],
      count: 1,
    })
    consoleError.mockRestore()
  })

  test('500 : throw + complete() PAS appelé (conserve → retry)', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    interceptUpload(() => new HttpResponse(null, { status: 500 }))

    await expect(uploadData(asPowerSync(db))).rejects.toThrow('sync/upload 500')
    expect(db.hasPendingCrud).toBe(true) // conservé pour retry
    expect(toastError).not.toHaveBeenCalled()
  })

  test('401 : throw + complete() PAS appelé', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    interceptUpload(() => new HttpResponse(null, { status: 401 }))

    await expect(uploadData(asPowerSync(db))).rejects.toThrow('sync/upload 401')
    expect(db.hasPendingCrud).toBe(true)
  })
})

describe('uploadData — gardes & sûreté-données', () => {
  test('batch vide : getCrudBatch null → no-op (aucun fetch, aucun complete)', async () => {
    const db = createMockPowerSync() // queue vide
    // Aucun handler installé : un fetch déclencherait l'erreur onUnhandledRequest de MSW.
    await expect(uploadData(asPowerSync(db))).resolves.toBeUndefined()
    expect(toastError).not.toHaveBeenCalled()
  })

  test('token absent : Authorization "Bearer " → (ici 401) throw, batch conservé', async () => {
    localStorage.clear() // pas de JWT
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    const captured = interceptUpload(() => new HttpResponse(null, { status: 401 }))

    await expect(uploadData(asPowerSync(db))).rejects.toThrow('sync/upload 401')
    // Token absent → header « Bearer » sans valeur (l'espace final est normalisé par undici).
    expect(captured[0]!.auth).toBe('Bearer')
    expect(db.hasPendingCrud).toBe(true)
  })

  test('header : la requête porte Authorization: Bearer <token>', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC])
    const captured = interceptUpload(() => HttpResponse.json([ok(rid(1))]))

    await uploadData(asPowerSync(db))
    expect(captured[0]!.auth).toBe('Bearer tok')
  })

  test('commit-partiel / replay : 500 puis 200 idempotent → MÊMES client_request_id, complete au 2ᵉ', async () => {
    const db = createMockPowerSync()
    db.enqueueCrud([PUT_ACC, PATCH_TX, DEL_SPLIT])
    // 1er appel 500, 2e appel 200 (les 3 ré-ackés idempotemment).
    const captured = interceptUpload((call) =>
      call === 1
        ? new HttpResponse(null, { status: 500 })
        : HttpResponse.json([ok(rid(1), { id: 'srv-1' }), ok(rid(2)), ok(rid(3))]),
    )

    // 1er appel : throw, rien purgé (le SDK re-invoquerait uploadData ; on le simule à la main).
    await expect(uploadData(asPowerSync(db))).rejects.toThrow('sync/upload 500')
    expect(db.hasPendingCrud).toBe(true)

    // 2e appel : le Mock re-sert le MÊME crud[] → mêmes client_request_id (anti double-write).
    await uploadData(asPowerSync(db))
    expect(db.hasPendingCrud).toBe(false)

    const ids1 = captured[0]!.body.mutations.map((m) => m.client_request_id)
    const ids2 = captured[1]!.body.mutations.map((m) => m.client_request_id)
    expect(ids2).toEqual(ids1)
    expect(ids1).toEqual([rid(1), rid(2), rid(3)])
  })
})
