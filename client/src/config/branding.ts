// ─────────────────────────────────────────────────────────────────────────────
// ⚠️  CHOIX DE MARQUE À VALIDER  — voir l'issue #240 (décisions UI/UX E15)
// ─────────────────────────────────────────────────────────────────────────────
// Source UNIQUE des chaînes de marque affichées dans le chrome (header / footer).
// Ce sont des DÉFAUTS posés par S15.1, pas une décision figée. À éditer ici (un seul
// endroit) une fois le nom / la tagline / le logo arrêtés.
//
// Le nom produit vit aussi à deux autres endroits hors de ce fichier (à aligner
// si on le change) : `client/index.html` (<title>) et `capacitor.config.ts` (appName).

/** Nom du produit affiché comme logo (texte ; pas de logo graphique pour l'instant). */
export const APP_NAME = 'Prosperity'

/** Tagline affichée dans le footer, à la suite du nom. */
export const APP_TAGLINE = 'gestion de budget familial'
