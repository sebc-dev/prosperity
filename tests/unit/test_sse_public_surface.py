"""Verrou de surface publique du module `sse` (S17.1, consumer-only).

`sse` siège au sommet du graphe directionnel et ne re-exporte RIEN : il consomme
des surfaces (auth, mini-bus) mais personne ne le consomme. Le broadcaster, la
livraison et les routes restent internes. Ce test casse si un `__all__` non vide
réapparaît — c'est-à-dire si un interne (le broadcaster surtout) fuit cross-module
(gabarit `test_sync_public_surface`)."""

from __future__ import annotations

import backend.modules.sse.public as sse_public


def test_sse_public_exposes_nothing() -> None:
    # Consumer-only : aucune surface exposée. Un re-export du broadcaster/délivrance
    # casserait ce verrou avant qu'un pair ne puisse l'importer.
    assert sse_public.__all__ == []
