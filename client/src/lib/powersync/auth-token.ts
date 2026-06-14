import { tokenStore } from '@/lib/auth/token-store'

// SOURCE UNIQUE du JWT pour la couche PowerSync, sans dépendance interne autre que le token-store
// leaf → le cycle ESM connector↔upload reste cassé (les deux importent ce module). Le JWT vit
// désormais EN MÉMOIRE (token-store), hydraté au boot depuis `lib/storage` (Secure Storage natif /
// localStorage web) par AuthProvider et rafraîchi par `lib/auth/session` : préemptif (setTimeout à
// exp − 60 s) ET réactif (`connector.fetchCredentials` rafraîchit avant de répondre au SDK). Lecture
// SYNC inchangée pour connector/upload.
//
// Le 401-retry des endpoints REST protégés (aucun en S14.6) arrivera en E15 (1er consommateur), via
// un middleware `onResponse` openapi-fetch single-flight ; le chemin live S14.6 (PowerSync) est déjà
// couvert par le refresh réactif de `fetchCredentials`.
export function getToken(): string | null {
  return tokenStore.getAccessToken()
}
