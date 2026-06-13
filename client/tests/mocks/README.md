# tests/mocks

Réservé au `MockPowerSyncDatabase` (stratégie de tests §5.3), **ajouté en S14.4** :
il exposera la même surface que `PowerSyncDatabase` avec des helpers
`simulateOffline()` / `simulateReconnect()` / `simulateSyncedFromServer(rows)` /
`simulateWriteResultError(code)` (cf. ADR 0014). La surface PowerSync étant définie
en S14.4, le mock vit là, pas ici.
