import {
  CrudBatch,
  CrudEntry,
  SyncStatus,
  UpdateType,
  type PowerSyncDatabase,
} from '@powersync/web'

// Double de test du `PowerSyncDatabase` (stratégie §5.3) — STATEFUL, pas de purs spies :
//   • connect/disconnect MUTENT `currentStatus.connected` (sinon « connecté stable » invérifiable) ;
//   • getCrudBatch() est IDEMPOTENT jusqu'à complete() (re-sert le MÊME crud[] → test replay) ;
//   • currentStatus porte la VRAIE shape `dataFlowStatus` (getter) — sinon le mock validerait le bug.
// Aucune connexion réelle (wasm/OPFS) en CI : toute la surface consommée est simulée ici.

type StatusListener = { statusChanged?: (status: SyncStatus) => void }

interface DataFlow {
  downloading: boolean
  uploading: boolean
}

export class MockPowerSyncDatabase {
  connectCount = 0
  disconnectCount = 0

  private _connected = false
  private _dataFlow: DataFlow = { downloading: false, uploading: false }
  private _lastSyncedAt: Date | undefined
  private readonly _listeners = new Set<StatusListener>()

  // Queue CRUD locale + drapeau de purge. getCrudBatch re-sert `_crud` tant que complete()
  // n'a pas été appelé (idempotence anti-double-write, cf. test replay).
  private _crud: CrudEntry[] = []

  // « Store local » par instance : deux instances = deux jeux de données isolés (AC « 2 users »
  // = isolation de CONTEXTE ; l'isolation réelle est validée serveur/Playwright). Smoke de
  // contexte volontairement découplé de la chaîne PowerSync→Drizzle réelle (requalifié, §3.6).
  private _syncedRows: unknown[] = []

  get currentStatus(): SyncStatus {
    return new SyncStatus({
      connected: this._connected,
      dataFlow: { downloading: this._dataFlow.downloading, uploading: this._dataFlow.uploading },
      lastSyncedAt: this._lastSyncedAt,
    })
  }

  registerListener(listener: StatusListener): () => void {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  }

  private _emit(): void {
    const status = this.currentStatus
    for (const l of this._listeners) l.statusChanged?.(status)
  }

  // --- Surface PowerSync consommée par le provider / l'upload --------------------------------

  connect(): Promise<void> {
    this.connectCount += 1
    this._connected = true
    this._emit()
    return Promise.resolve()
  }

  disconnect(): Promise<void> {
    this.disconnectCount += 1
    this._connected = false
    this._emit()
    return Promise.resolve()
  }

  getCrudBatch(): Promise<CrudBatch | null> {
    if (this._crud.length === 0) return Promise.resolve(null)
    const complete = (): Promise<void> => {
      this._crud = [] // purge : le prochain getCrudBatch() renverra null
      return Promise.resolve()
    }
    // Nouveau CrudBatch à chaque appel mais MÊME crud[] tant que complete() n'a pas vidé la
    // queue → un 2ᵉ uploadData (après un throw sans complete) relit les mêmes entrées.
    return Promise.resolve(new CrudBatch([...this._crud], false, complete))
  }

  // --- Leviers de test ----------------------------------------------------------------------

  /** Remet l'instance à neuf (le mock est partagé via le module mocké → hygiène inter-tests). */
  reset(): void {
    this.connectCount = 0
    this.disconnectCount = 0
    this._connected = false
    this._dataFlow = { downloading: false, uploading: false }
    this._lastSyncedAt = undefined
    this._crud = []
    this._syncedRows = []
    this._listeners.clear()
  }

  /** Amorce la queue CRUD (fixtures d'upload). */
  enqueueCrud(entries: CrudEntry[]): void {
    this._crud = [...entries]
  }

  /** True tant que la queue n'a pas été purgée par complete(). */
  get hasPendingCrud(): boolean {
    return this._crud.length > 0
  }

  simulateOffline(): void {
    this._connected = false
    this._emit()
  }

  simulateReconnect(): void {
    this._connected = true
    this._emit()
  }

  /** Pilote `dataFlowStatus` (download/upload en cours) pour les 3 états de `useSyncStatus`. */
  simulateDataFlow(flow: Partial<DataFlow>): void {
    this._dataFlow = { ...this._dataFlow, ...flow }
    this._emit()
  }

  simulateSyncedFromServer(rows: unknown[]): void {
    this._syncedRows = [...rows]
    this._lastSyncedAt = new Date()
    this._emit()
  }

  getSyncedRows(): unknown[] {
    return this._syncedRows
  }
}

/** Fabrique castée à la surface attendue par les consommateurs (provider, hooks, upload). */
export function createMockPowerSync(): MockPowerSyncDatabase {
  return new MockPowerSyncDatabase()
}

/** Construit une `CrudEntry` réaliste (op/table/id/clientId/opData) pour les fixtures d'upload. */
export function crudEntry(args: {
  clientId: number
  op: UpdateType
  table: string
  id: string
  opData?: Record<string, unknown>
}): CrudEntry {
  return new CrudEntry(args.clientId, args.op, args.table, args.id, undefined, args.opData)
}

/** Cast d'usage : le mock satisfait la surface consommée de `PowerSyncDatabase`. */
export function asPowerSync(mock: MockPowerSyncDatabase): PowerSyncDatabase {
  return mock as unknown as PowerSyncDatabase
}
