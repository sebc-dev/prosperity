"""Domaine du module `sync` — délibérément vide en V1 (S13.2 / P13.2.1).

`sync` n'a pas d'agrégat propre : par l'ADR 0014, le dispatcher (S13.3) et les
sous-handlers par table (S13.4) orchestrent les `service.py` des modules métier
via leur `public.py` — toute règle domaine vit là, jamais ici. La seule matière
persistée de `sync` est le journal d'idempotence (`models.SyncRequestLog`) ; le
contrat de transport (l'enveloppe batch PowerSync) est dans `schemas.py`. Ce
fichier existe pour matérialiser la couche et documenter cette vacuité
(placeholder ; aucune entité n'y est définie tant qu'un besoin n'émerge pas).
"""

from __future__ import annotations
