"""Surface publique du module `sse` — **consumer-only** (S17.1, ADR 0012).

`sse` siège au sommet du graphe directionnel (ADR 0005, contrat 1, couche
`sync | savings | sse`) : il consomme le `public.py` des modules métier (auth pour
le token, le mini-bus de `shared` pour les signaux) mais **personne ne le consomme**.
Le broadcaster, la livraison et les routes restent INTERNES — seul le composition
root (`backend/main.py`) touche `sse.transports.http.sse_router` et
`sse.service.delivery.register_sse_delivery`, via des imports directs (pas cette
surface). `__all__` est donc volontairement **vide** : c'est un verrou anti-fuite
(`test_sse_public_surface`) garantissant qu'aucun interne (le broadcaster surtout)
n'est exposé cross-module.
"""

from __future__ import annotations

__all__: list[str] = []
