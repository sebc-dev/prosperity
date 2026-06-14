import type { StorageBackend } from './types'

// Backend web : localStorage enrobé en Promise (dénominateur commun de l'API async, D1).
// Convient au dev et au navigateur (pas de Keystore côté web → résiduel XSS inhérent, hors-MVP).
export const webBackend: StorageBackend = {
  get: (key) => Promise.resolve(localStorage.getItem(key)),
  set: (key, value) => Promise.resolve(localStorage.setItem(key, value)),
  remove: (key) => Promise.resolve(localStorage.removeItem(key)),
}
