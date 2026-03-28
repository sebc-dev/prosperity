# ADR-0001 : Stack technique initiale

## Statut
Accepte -- 2026-03-27

## Contexte
Application de gestion de finances personnelles self-hosted pour un foyer. Projet open source, pas de deadline. Contraintes imposees : Java, Angular, PostgreSQL, Plaid (EU/FR). Contrainte supplementaire : les versions choisies doivent etre supportees par l'outillage CI/lint (pas de bleeding edge).

## Decision

### Backend
- **Java 21 LTS** au lieu de Java 25 LTS : Checkstyle ne supporte pas encore la grammaire Java 25 (mars 2026). SonarQube necessite la version 2026.2. Java 21 offre un support outillage complet.
- **Spring Boot 4.0.x** au lieu de 3.5.x : Spring Boot 3.5 OSS finit en juin 2026, forcerait une migration rapide. Boot 4.0 offre un support jusqu'a ~nov 2027.
- **Flyway 11.x** (Apache 2.0) au lieu de Liquibase 5.0.x : Liquibase 5.0 a change de licence vers FSL (pas open source). Flyway Community reste Apache 2.0, integre nativement avec Spring Boot 4.

### Frontend
- **Angular 21** + **pnpm** : derniere stable, pnpm est le default Angular 21.
- **PrimeNG 21.x** au lieu d'Angular Material : meilleur ratio composants finance (p-inputnumber monetaire, p-table complet) / compatibilite AI code generation / integration Tailwind v4. Angular Material domine le corpus AI (2.3M dl/sem) mais manque de composants finance (pas de currency input, table basique).
- **ngx-echarts 21.x** au lieu de ng2-charts : seule option avec candlestick natif, dataZoom, 30+ types. ngx-charts (Swimlane) elimine (pas de support Angular 21, maintenance en declin).
- **Tailwind CSS v4 + tailwindcss-primeui** : layout en Tailwind, composants PrimeNG. Spartan UI (headless + Tailwind) rejete : alpha, 1 mainteneur, corpus AI quasi nul.

### Synchro bancaire
- **Plaid** comme fournisseur principal : SG et Banque Populaire confirmees. Interface abstraite prevue pour interchangeabilite (Powens, Salt Edge en fallback).
- **GoCardless/Nordigen** elimine : ferme aux nouveaux inscrits depuis juillet 2025.

## Alternatives considerees
| Alternative | Rejetee car |
|-------------|-------------|
| Java 25 LTS | Checkstyle incompatible, SonarQube necessite upgrade |
| Spring Boot 3.5.x | Fin OSS juin 2026, migration forcee |
| Angular Material | Composants finance insuffisants (pas de currency input, table basique) |
| Spartan UI | Alpha, 1 mainteneur, pas de corpus AI |
| ngx-charts (Swimlane) | Pas de support Angular 21, maintenance en declin |
| GoCardless/Nordigen | Ferme aux nouveaux inscrits (juillet 2025) |

## Consequences

### Positives
- Stack avec support long terme (Java 21 → sept 2028, Boot 4.0 → nov 2027, PG 17 → nov 2029)
- Outillage CI/lint 100% compatible
- PrimeNG reduit le code custom pour les composants finance
- Interface abstraite connecteur bancaire permet de changer de fournisseur

### Negatives / Trade-offs
- Java 21 n'a pas les features de Java 25 (virtual threads sans pinning, flexible constructors)
- PrimeNG a un corpus AI plus petit qu'Angular Material (~300K vs 2.3M dl/sem)
- ECharts plus lourd que Chart.js (~120-150 kB vs ~70 kB gzip apres tree-shaking)

### Risques associes
- Plaid FR couverture partielle, paysage volatile (cf. fermeture Nordigen)
- Spring Boot 4.0 est relativement recent (nov 2025), breaking changes possibles dans les minor
