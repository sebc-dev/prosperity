"""Entrypoints CLI hors-requête (jobs cron CI, maintenance).

`backend.scripts.*` est du code de PROD (mesuré par la couverture, `source =
["backend"]`), pas un dossier de tests : chaque entrypoint a son test
d'intégration (gabarit `purge_sync_request_log` ↔ `test_purge_script`).
"""
