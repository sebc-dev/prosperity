import type { WriteErrorCode } from './protocol'

// Messages utilisateur (FR) MAPPÉS depuis le `code` typé — JAMAIS le `message` serveur
// (anti-fuite : `error.message` peut porter du détail interne). `GENERIC` = fallback si le
// serveur évolue et renvoie un code inconnu (cf. `?? GENERIC` dans upload.ts).
export const GENERIC = 'Une erreur est survenue.'

export const WRITE_ERROR_MESSAGES: Record<WriteErrorCode, string> = {
  auth_denied: 'Action non autorisée.',
  unknown_table: 'Type de données non reconnu.',
  not_implemented_yet: 'Cette fonctionnalité n’est pas encore disponible.',
  validation_error: 'Données invalides.',
  immutable_field_violation: 'Ce champ ne peut pas être modifié.',
  uncategorized_expense: 'Cette dépense doit être catégorisée.',
  unbalanced_transaction: 'La transaction n’est pas équilibrée.',
  invalid_state_transition: 'Ce changement d’état n’est pas autorisé.',
  not_found: 'Élément introuvable.',
}
