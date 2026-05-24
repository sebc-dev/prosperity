# Génération des récurrences : cron serveur exclusif, horizon = fin du mois

F06 spécifie qu'une modification de règle de récurrence ne touche que les occurrences "non encore générées", mais ne tranche ni le producteur (serveur ? client ? lazy ?), ni la définition opérationnelle de "non encore générée" sous multi-device offline-first. Nous décidons que la génération est **exclusivement serveur via cron nightly** (APScheduler), avec un **horizon de matérialisation = fin du mois en cours** (identique à l'horizon du solde projeté), via un job **idempotent** clé `(recurring_rule_id, occurrence_date)` (`INSERT ... ON CONFLICT DO NOTHING`). "Non encore générée" se définit alors mécaniquement : *absence en DB au moment de l'exécution du cron suivant*. Les projections au-delà de l'horizon (`forecasting/`, `savings/`) sont calculées à la volée par une fonction pure `forecast_with_recurrings(date_start, date_end)` et ne sont jamais persistées ni synchronisées.

## Consequences

- **Pas de génération côté client**, pas de génération lazy. Élimine les conflits multi-device dès l'origine.
- Le comportement "modif avant cron / après cron" doit être documenté dans `runbooks/recurring_rules.md` : heure du cron (ex. 02:00 UTC), exemples concrets, marche à suivre si l'utilisateur veut appliquer une modif à une occurrence déjà matérialisée (édition individuelle de l'occurrence).
- Conséquence offline-first : une **nouvelle règle** créée en offline ne génère pas d'occurrences tant que (i) le sync atteint le serveur, (ii) le cron suivant tourne. Acceptable car les premières occurrences sont typiquement à plusieurs jours.
- Le module `forecasting/` expose `forecast_with_recurrings()` dans son `public.py` ; le module `savings/` l'importe pour ses projections d'objectifs.
- Versioning de la règle : audit trail sur la table `recurring_rules`, suffisant car les occurrences matérialisées sont autonomes (snapshot du template au moment de la génération).
