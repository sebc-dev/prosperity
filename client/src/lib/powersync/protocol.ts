// Types WIRE du write upload handler — mirror EXACT de `backend/modules/sync/schemas.py`
// (ADR 0014). Aucune logique métier : juste le format de transport `POST /sync/upload`.
// `WriteErrorCode` est le vocabulaire FERMÉ (Literal côté serveur) — `internal_error` n'y
// figure PAS (une erreur serveur non mappée propage en HTTP 500, pas un code).

export type MutationOp = 'insert' | 'update' | 'delete'

export type WriteErrorCode =
  | 'auth_denied'
  | 'unknown_table'
  | 'not_implemented_yet'
  | 'validation_error'
  | 'immutable_field_violation'
  | 'uncategorized_expense'
  | 'unbalanced_transaction'
  | 'invalid_state_transition'
  | 'not_found'

export interface Mutation {
  client_request_id: string
  table: string
  op: MutationOp
  payload: Record<string, unknown>
}

export interface BatchUpload {
  mutations: Mutation[]
}

export interface WriteError {
  code: WriteErrorCode
  message: string
}

export interface WriteResult {
  client_request_id: string
  success: boolean
  error?: WriteError | null
  server_values?: Record<string, unknown> | null
}
