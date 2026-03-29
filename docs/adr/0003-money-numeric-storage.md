# ADR-0003 : Stockage monetaire en NUMERIC(19,4) au lieu de BIGINT centimes

## Statut
Accepte -- 2026-03-29

## Contexte
La v1 stockait les montants monetaires en BIGINT representant des centimes (ex: 4250 pour 42.50 EUR).
Ce pattern, courant dans les systemes multi-devises comme Stripe, introduit de la complexite inutile
pour Prosperity :

- Un `MoneyConverter` JPA devait traduire entre `Money` (BigDecimal) et `Long` (centimes)
- Les requetes SQL directes affichaient des centimes, pas des montants lisibles
- Les agregations SQL (`SUM`, `AVG`) necessitaient une division par 100
- Le diviseur depend de la devise (100 pour EUR, 1 pour JPY, 1000 pour BHD), ajoutant
  de la complexite sans valeur pour un projet actuellement mono-devise

## Decision
Stocker les montants monetaires en `NUMERIC(19,4)` dans PostgreSQL :

- **19 chiffres de precision** : couvre largement les montants financiers personnels
- **4 decimales** : couvre toutes les devises ISO 4217 (EUR=2, BHD=3, plus une marge)
- Le value object `Money` conserve un `BigDecimal` interne, normalise a scale 4
- Le `MoneyConverter` JPA traduit simplement `Money` <-> `BigDecimal` (pas de conversion centimes)
- La validation de precision par devise sera geree dans `Money` lors de l'ajout du multi-devise

## Consequences

### Positif
- Les requetes SQL sont lisibles directement (`SELECT balance FROM bank_accounts` affiche `42.5000`)
- Les agregations SQL fonctionnent sans transformation (`SUM(balance)`)
- Le converter est trivial (delegation directe BigDecimal, pas de multiplication/division)
- `Money.equals()` est coherent grace a la normalisation de scale
- Prepare le multi-devise sans refactoring du stockage (NUMERIC(19,4) couvre toutes les devises ISO 4217)

### Negatif
- Les montants affichent 4 decimales en SQL meme pour EUR (cosmétique, sans impact fonctionnel)
- Migration necessaire pour les bases existantes (V007)

## Alternatives considerees

| Option | Rejetee car |
|--------|-------------|
| BIGINT centimes | Complexite de conversion, SQL illisible, diviseur variable par devise |
| NUMERIC(19,2) | Insuffisant pour BHD (3 decimales) et autres devises exotiques |
| DECIMAL (synonyme) | Equivalent a NUMERIC en PostgreSQL, mais NUMERIC est le terme standard SQL |
