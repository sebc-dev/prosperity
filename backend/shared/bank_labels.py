"""Normalisation canonique de libellé bancaire + hash composite de dedup.

`normalize_label` est la normalisation de référence — strip + lowercase +
retrait des préfixes bancaires standard (`PRLV SEPA`, `CB`, `VIR`, `PAIEMENT`)
+ retrait des dates ISO — partagée par la dedup OFX (S12.3) ET le futur
`MatchScorer` du module `reconciliation` (CONTEXT.md §MatchScorer), pour
garantir une dedup et un matching strictement cohérents.

`import_hash` dérive un sha256 déterministe de `(account_id, date,
amount_cents, libellé_normalisé)` — FITID JAMAIS utilisé (doctrine F04).

Couche `shared/` : n'importe RIEN de `backend.modules.*` (import-linter #3) ;
stdlib seul. ⚠️ Le format de sérialisation du hash est PERSISTÉ
(`imported_transactions.import_hash`) — le modifier casserait la dedup de
l'historique. Verrouillé par un test à vecteur connu.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from uuid import UUID

# Préfixes bancaires standard (CONTEXT.md §MatchScorer). Ordre = plus longs
# d'abord pour que "prlv sepa" l'emporte sur "prlv" / "vir sepa" sur "vir" DANS
# la même itération (verrouillé par test, cf. `test_prefix_order_longest_first`).
# Retirés en TÊTE, en boucle (un libellé peut cumuler "VIR SEPA CB ...").
_BANK_PREFIXES: tuple[str, ...] = ("prlv sepa", "vir sepa", "prlv", "vir", "paiement", "cb")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Contrôles C0 + DEL + surrogates isolés retirés EXPLICITEMENT (D2) : ne pas
# dépendre du seul fait que `\s` couvre \x1c–\x1f en CPython — garantit que le
# séparateur \x1f du hash ne peut jamais apparaître dans un libellé normalisé
# (injection-safety). Les surrogates isolés (\ud800–\udfff) sont aussi retirés :
# ils ne sont pas couverts par `\s`/C0 et feraient lever `UnicodeEncodeError` à
# l'encodage UTF-8 du payload (`import_hash`) — la sortie normalisée doit donc
# toujours être encodable en UTF-8.
_CTRL = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff]")
_WS = re.compile(r"\s+")


def normalize_label(raw: str) -> str:
    """Normalisation canonique d'un libellé bancaire (cf. MatchScorer).

    strip + lowercase + retrait dates ISO + suppression de tous les contrôles
    C0/DEL + surrogates isolés + retrait répété des préfixes bancaires en tête
    (plus longs d'abord) + collapse du whitespace. La sortie est toujours
    encodable en UTF-8. Idempotente. `"" → ""`, `"   " → ""`.
    """
    s = raw.strip().lower()
    s = _ISO_DATE.sub(" ", s)  # dates ISO retirées (où qu'elles soient)
    s = _CTRL.sub(" ", s)  # contrôles C0/DEL + surrogates → espace (anti-\x1f / UTF-8 safe)
    changed = True
    while changed:  # retrait répété des préfixes en tête
        changed = False
        s = s.strip()
        for prefix in _BANK_PREFIXES:
            if s == prefix or s.startswith(prefix + " "):
                s = s[len(prefix) :]
                changed = True
                break
    return _WS.sub(" ", s).strip()  # whitespace collapsé → pas de \x1f résiduel


def import_hash(account_id: UUID, date: dt.date, amount_cents: int, normalized_label: str) -> str:
    """sha256 hex (64 car. minuscules) de la sérialisation canonique D2.

    ⚠️ `normalized_label` DOIT être une sortie de `normalize_label` : la fonction
    ne re-normalise pas (l'appelant le fait une fois). Format PERSISTÉ → verrouillé
    par `test_known_vector`. C'est un hash de dedup métier, pas une primitive crypto.

    Défense en profondeur : l'encodage utilise `surrogatepass` pour qu'un surrogate
    isolé (qu'un appelant indiscipliné pourrait laisser passer) ne fasse jamais
    lever `UnicodeEncodeError` sur cette primitive persistée. N'affecte aucun
    vecteur sans surrogate (le format historique est inchangé) ; `normalize_label`
    retire déjà ces surrogates en amont du chemin de dedup.
    """
    payload = "\x1f".join((str(account_id), date.isoformat(), str(amount_cents), normalized_label))
    return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()
