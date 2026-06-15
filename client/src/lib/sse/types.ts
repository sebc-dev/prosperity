// Types publics du wrapper SSE (`lib/sse`). Le wrapper est framework-agnostique :
// `hooks/useSse` (E15) ne sera qu'un mince adaptateur React par-dessus `createSseClient`.

// États observables du flux. `idle` avant `start()` ; `unauthenticated` = auth définitivement
// perdue (le refresh a échoué) → l'UI (E15) redirige vers /login ; `closed` après `stop()`.
export type SseState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'unauthenticated'
  | 'closed'

// Un event métier livré aux abonnés. `data` est déjà `JSON.parse`é (les frames au JSON invalide
// sont ignorées, jamais livrées). `id` est l'id serveur monotone (null pour une frame sans id).
export interface SseEvent {
  id: string | null
  event: string
  data: unknown
}

export interface SseClientOptions {
  // Défaut `import.meta.env.VITE_API_BASE_URL`. Surchargé en test.
  baseUrl?: string
  // Marge (s) avant l'expiration du token pour roter proactivement. Défaut 60 (TTL serveur 300).
  tokenTtlMarginSeconds?: number
  // Plafond du backoff de reconnexion (ms). Défaut 30_000.
  maxBackoffMs?: number
  // Durée minimale (ms) d'une connexion « saine ». Une connexion qui se ferme (EOF serveur) avant
  // ce seuil déclenche un backoff anti-spin (open→EOF immédiat répété = misconfig/overflow). Défaut
  // 1000. Mettre 0 désactive l'anti-spin (reconnexion immédiate sur EOF).
  minHealthyMs?: number
  // Garder le flux ouvert quand l'onglet/app est caché. Défaut `false` (conservateur : évite de
  // drainer la batterie mobile et de saturer le plafond de connexions serveur). E15 tranchera.
  openWhenHidden?: boolean
}

export interface SseClient {
  // Démarre le cycle de vie (acquisition token → stream → reconnexion). Idempotent.
  start(): void
  // Arrête définitivement (abort + purge des timers). Non redémarrable.
  stop(): void
  getState(): SseState
  // Abonnement à un type d'event métier (`event:` de la frame). Renvoie un désabonnement.
  subscribe(eventType: string, handler: (e: SseEvent) => void): () => void
  // Notifié quand le serveur signale une désynchro (`event: resync`) : l'appelant doit re-sync
  // via REST/PowerSync. Distinct de `subscribe` (resync n'est pas une donnée métier).
  onResync(handler: () => void): () => void
  // Notifié à chaque transition d'état (pour un badge de connexion en E15).
  onStateChange(handler: (s: SseState) => void): () => void
}
