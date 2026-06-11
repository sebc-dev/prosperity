"""Nettoyage des textes libres *imposés à un tiers* (frontières d'écriture).

Source UNIQUE du whitelist appliqué à un texte qu'un utilisateur impose à un
autre — le `short_label` d'une `ShareRequest` (imposé au débiteur), la `note`
d'un `Settlement`. Caractères autorisés : ASCII imprimable (0x20–0x7E) + Latin-1
imprimable (0xA1–0xFF), moins SHY (U+00AD, un `Cf`). Bloque PAR CONSTRUCTION les
caractères de contrôle / format (Cc/Cf — overrides BiDi U+202E…, zero-width
joiners, NBSP & tout `Zs` ≠ espace), exclut `\\n`/`\\t` (texte single-line ⇒
anti-injection), et tout script non-latin (anti-homoglyphe / anti-spoofing).
Patron de `auth.schemas._DEVICE_LABEL_ALLOWED`, ÉTENDU au Latin-1 (accents FR).

⚠️ Les DEUX frontières d'écriture DOIVENT passer un texte imposé par ici : le
boundary REST (`debts.schemas`) ET le boundary sync (`sync.handlers.payloads`).
Une seconde frontière plus laxiste laisserait un client sync persister ce que
HTTP rejette (reviews #22/#144 ; stored-XSS en WebView Capacitor côté rendu).
Le whitelist borne l'entrée serveur-side ; le rendu client reste tenu d'échapper.
"""

from __future__ import annotations

IMPOSED_TEXT_ALLOWED = frozenset(chr(c) for c in (*range(0x20, 0x7F), *range(0xA1, 0x100))) - {
    chr(0xAD)  # SHY (soft hyphen, un Cf format char)
}


def clean_imposed_text(value: str, *, field: str) -> str:
    """Trim + validation whitelist d'un texte libre imposé à un tiers (champ
    REQUIS). Lève `ValueError` (→ `ValidationError` Pydantic) si vide après trim
    ou si un caractère hors whitelist est présent. Renvoie la valeur trimmée."""
    value = value.strip()
    if not value:  # vide après trim → rejet
        raise ValueError(f"{field} must not be blank")
    if any(c not in IMPOSED_TEXT_ALLOWED for c in value):
        raise ValueError(f"{field} contains a disallowed character")
    return value


def clean_optional_imposed_text(value: str | None, *, field: str) -> str | None:
    """Variante d'un champ OPTIONNEL (gabarit `Settlement.note`) : `None` ou vide
    après trim → `None` ; sinon trim + validation whitelist (lève si caractère
    interdit)."""
    if value is None:
        return None
    value = value.strip()
    if not value:  # vide après trim → champ optionnel absent
        return None
    if any(c not in IMPOSED_TEXT_ALLOWED for c in value):
        raise ValueError(f"{field} contains a disallowed character")
    return value
