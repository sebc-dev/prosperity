import type { AbstractPowerSyncDatabase } from '@powersync/web'

// SQUELETTE P14.4.1 — câble `connector.uploadData` pour que le provider/connecteur
// compilent (branche verte). Le handler RÉEL (mapping CrudEntry→Mutation, POST /sync/upload,
// switch HTTP D7, toasts mappés, adoption d'id D9) est implémenté en P14.4.2.
//
// PowerSync ré-invoque `uploadData` jusqu'à vidage de la queue ; ce no-op transitoire ne
// purge rien (pas de `complete()`) → aucune écriture perdue avant P14.4.2.
export async function uploadData(db: AbstractPowerSyncDatabase): Promise<void> {
  // Lecture seule du batch, SANS complete() ni POST → rien n'est purgé ni perdu. Le traitement
  // complet (mapping, POST /sync/upload, switch HTTP, toasts, adoption d'id) arrive en P14.4.2.
  await db.getCrudBatch()
}
