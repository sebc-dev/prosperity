import { UpdateType, type AbstractPowerSyncDatabase, type CrudEntry } from '@powersync/web'
import { toast } from 'sonner'
import { v5 as uuidv5 } from 'uuid'

import { adoptServerValues } from './adopt'
import { getToken } from './auth-token'
import { GENERIC, WRITE_ERROR_MESSAGES } from './error-messages'
import type { BatchUpload, Mutation, WriteResult } from './protocol'

// Namespace UUID PUBLIC (non secret) pour dériver un `client_request_id` DÉTERMINISTE et
// STABLE par opération : `uuidv5(clientId, NS)`. `clientId` (auto-incrément par op, stable
// across-retries) porte l'idempotence — la même op ré-émise après un échec produit le MÊME
// id, que le serveur déduplique (scope `(user_id, client_request_id)`, ADR 0014).
export const NS = '2f9a7b14-6c3e-4d8a-9f1b-0c5e7a2d3b46'

const OP = {
  [UpdateType.PUT]: 'insert',
  [UpdateType.PATCH]: 'update',
  [UpdateType.DELETE]: 'delete',
} as const

const reqId = (e: CrudEntry): string => uuidv5(String(e.clientId), NS)

function toMutation(e: CrudEntry): Mutation {
  const op = OP[e.op]
  const opData: Record<string, unknown> = e.opData ?? {}
  // insert : on OMET `id` (généré serveur, renvoyé via server_values). update/delete : on
  // joint l'id de la row (PowerSync est client-id-authoritative sur les rows existantes).
  const payload = op === 'insert' ? { ...opData } : { id: e.id, ...opData }
  return { client_request_id: reqId(e), table: e.table, op, payload }
}

export async function uploadData(db: AbstractPowerSyncDatabase): Promise<void> {
  const batch = await db.getCrudBatch()
  if (!batch) return // queue vide → no-op (pas de fetch, pas de complete)

  // Corrélation result↔entry par `client_request_id` (le serveur renvoie 1 WriteResult/mutation,
  // ordre préservé mais on JOINT par id pour ne dépendre d'aucun ordre — AC load-bearing).
  const byId = new Map(batch.crud.map((e) => [reqId(e), e]))
  const body: BatchUpload = { mutations: batch.crud.map(toMutation) }

  const apiBase = import.meta.env.VITE_API_BASE_URL as string
  const res = await fetch(`${apiBase}/sync/upload`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Token UNIQUEMENT en header Authorization (jamais en URL/query).
      Authorization: `Bearer ${getToken() ?? ''}`,
    },
    body: JSON.stringify(body),
  })

  // --- Classification HTTP (D7) — purge vs retry ------------------------------------------
  // 401 : transitoire → on throw ; PowerSync re-`fetchCredentials`. ⚠️ S14.4 : token statique
  // (refresh réel = S14.6) → un 401 boucle jusqu'au refresh ; NON destructeur (rien n'est
  // purgé). Résiduel assumé, tracé §7 du plan.
  if (res.status === 401) throw new Error('sync/upload 401')

  // 400/422 : `extra="forbid"` côté serveur → rejet de FORME PERMANENT (batch ré-émis
  // identique → boucle infinie si on retry). On PURGE (complete) pour ne pas bloquer la queue
  // (anti poison-message / DoS sync). Un tel 400/422 = bug de NOTRE client (mapping/payload),
  // diagnosticable en dev SANS jamais logger le payload (PII).
  if (res.status === 400 || res.status === 422) {
    if (import.meta.env.DEV) {
      console.error('[powersync] rejet de forme — purge', {
        status: res.status,
        client_request_ids: body.mutations.map((m) => m.client_request_id),
        count: body.mutations.length,
      })
    }
    toast.error(GENERIC)
    await batch.complete()
    return
  }

  // 5xx / réseau / autres : transitoire → throw SANS complete → PowerSync retry ; les mutations
  // 1..N-1 déjà committées au 500 sont ré-ackées idempotemment au prochain essai.
  if (!res.ok) throw new Error(`sync/upload ${res.status}`)

  // 200 : un WriteResult par mutation. On route chacun vers SA CrudEntry (via byId).
  const results = (await res.json()) as WriteResult[]
  for (const r of results) {
    if (!r.success && r.error) {
      // Message MAPPÉ FR depuis le code (jamais `error.message` serveur) ; fallback si code inconnu.
      toast.error(WRITE_ERROR_MESSAGES[r.error.code] ?? GENERIC)
    } else if (r.success && r.server_values) {
      const entry = byId.get(r.client_request_id) // corrélation ; ignore un id orphelin
      if (entry) adoptServerValues(entry, r.server_values) // capture observable de l'id serveur (D9)
    }
  }
  await batch.complete() // purge le batch traité (typed-errors incluses : permanentes)
}
