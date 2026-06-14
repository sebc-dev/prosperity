import type { StorageBackend } from './types'

// Backend web : localStorage enrobé en Promise (dénominateur commun de l'API async, D1).
// Convient au dev et au navigateur (pas de Keystore côté web → résiduel XSS inhérent, hors-MVP).
//
// POSTURE MVP ASSUMÉE (S14.6) : le refresh token (TTL ~30 j) y est persisté côté web. Un vol XSS
// du refresh = compromission persistante malgré la rotation (l'attaquant rafraîchit en boucle).
// Accepté pour le MVP (offline-first, pas de backend de session web ; mobile = Secure Storage).
// Durcissement reporté : refresh en cookie HttpOnly+SameSite côté backend, ou TTL web réduit.
export const webBackend: StorageBackend = {
  get: (key) => Promise.resolve(localStorage.getItem(key)),
  set: (key, value) => Promise.resolve(localStorage.setItem(key, value)),
  remove: (key) => Promise.resolve(localStorage.removeItem(key)),
}
