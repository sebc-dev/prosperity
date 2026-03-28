# SPEC.md -- Prosperity

## Objectif
Mon foyer ne peut pas gerer convenablement ses finances (suivi, categorisation, budgets enveloppes, multi-comptes) parce qu'on fait tout de tete, et avec un projet immobilier qui va augmenter les charges mensuelles, ce n'est plus tenable.

## Utilisateur cible
Foyer (N utilisateurs) gerant leurs finances personnelles communes sur une instance self-hosted. Modele de droits multi-utilisateurs (open source).

## Fonctionnalites MVP

### F1: Authentification
- [ ] Login / logout avec JWT via BFF cookie flow (cookies httpOnly)
- [ ] Refresh token gere cote serveur
- [ ] Protection CSRF active
- [ ] Session multi-device supportee

### F2: Administration
- [ ] CRUD utilisateurs avec attribution de roles
- [ ] Attribution des droits de creation de comptes bancaires
- [ ] Gestion globale des connexions Plaid (ajout/suppression d'institutions)
- [ ] Dashboard monitoring systeme (health, connexions actives)

### F3: Creation de comptes bancaires
- [ ] Creation de comptes personnels (un seul proprietaire)
- [ ] Creation de comptes communs (N utilisateurs partageants)
- [ ] Distinction visuelle perso / commun

### F4: Gestion des acces aux comptes bancaires
- [ ] Droits par utilisateur et par compte (lecture, ecriture, admin)
- [ ] Un utilisateur ne voit que les comptes auxquels il a acces

### F5: Budgets enveloppes
- [ ] Creation d'enveloppes par compte (perso ou commune, parametrable)
- [ ] Allocation de montant par enveloppe
- [ ] Rollover parametrable par enveloppe : report auto ou remise a zero
- [ ] Visualisation consommation vs budget

### F6: Gestion de dette interne
- [ ] Suivi des dettes entre utilisateurs
- [ ] Objectif = remboursement (solde a zero)
- [ ] Historique long terme des remboursements
- [ ] Calcul automatique depuis les transactions sur comptes communs

### F7: Import de transactions (Plaid)
- [ ] Connexion a une institution bancaire via Plaid
- [ ] Import automatique des transactions (mode batch)
- [ ] Import initial avec profondeur parametrable
- [ ] Detection de doublons a l'import
- [ ] Interface abstraite connecteur bancaire (Plaid interchangeable)

### F8: Saisie manuelle + pointage
- [ ] Saisie manuelle de transactions (especes, virements entre comptes)
- [ ] Transactions recurrentes optionnelles (loyer, abonnements)
- [ ] Pointage de transactions (saisie et importee) : rapprochement bancaire

### F9: Dashboard
- [ ] Vue consolidee des soldes de tous les comptes accessibles
- [ ] Graphiques budgets enveloppes (consommation vs allocation)
- [ ] Graphiques evolution des soldes dans le temps
- [ ] Resume des transactions recentes

### F10: Backup PostgreSQL
- [ ] pg_dump planifie (cron ou Spring scheduler)
- [ ] Stockage local des dumps avec rotation

## Stack
| Composant | Technologie | Version |
|-----------|-------------|---------|
| Backend | Java (Temurin) + Spring Boot | 21 LTS + 4.0.x |
| ORM | Spring Data JPA | 4.0.x |
| Security | Spring Security | 7.0.x |
| Migrations | Flyway | 11.x |
| Database | PostgreSQL | 17 |
| Frontend | Angular + PrimeNG + Tailwind v4 | 21 + 21.x + v4 |
| Charts | ngx-echarts (Apache ECharts) | 21.x |
| Package manager | pnpm | latest |
| Runtime | Node.js | 22 LTS |
| Reverse proxy | Caddy | 2.10.x |
| Bank sync | Plaid API (EU/FR) | -- |
| Deploy | Docker Compose | -- |

## Contraintes
- Self-hosted Ubuntu (4c, 24 Go RAM)
- Open source (MIT/Apache 2.0 deps only)
- Outillage CI/lint mature (pas de bleeding edge)
- Connecteur bancaire abstrait (Plaid interchangeable)

## Hors scope (v1)
| Exclu | Raison |
|-------|--------|
| App native iOS/Android | PWA couvre le besoin |
| Multi-devises | Euros uniquement |
| Multi-foyers / SaaS | Self-hosted, un foyer |
