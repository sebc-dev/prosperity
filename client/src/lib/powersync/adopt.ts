// Adoption d'id (D9) — CAPTURE observable, pas convergence. Un `insert` réussi renvoie un
// `server_values.id` (id serveur autoritaire) ; on l'émet vers un sink injectable (no-op par
// défaut, substituable en test). La convergence end-to-end (orphelin local client-id ↔ row
// canonique server-id, FK) est HORS-S14.4 : elle arrive par download + est validée en
// Playwright/intégration + property tests serveur (S13.9).

export interface AdoptedId {
  table: string
  localId: string
  serverId: string
}

export type AdoptSink = (e: AdoptedId) => void

let _sink: AdoptSink = () => {}

export function setAdoptSink(sink: AdoptSink): void {
  _sink = sink
}

export function adoptServerValues(
  entry: { table: string; id: string },
  values: Record<string, unknown>,
): void {
  if (typeof values.id === 'string') {
    _sink({ table: entry.table, localId: entry.id, serverId: values.id })
  }
}
