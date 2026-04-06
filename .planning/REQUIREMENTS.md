# Requirements: Prosperity

**Defined:** 2026-03-28
**Core Value:** Un foyer peut suivre ses finances au quotidien (soldes, transactions, budgets enveloppes) sans effort manuel excessif, grace a la synchronisation bancaire automatique et une interface claire.

## v1 Requirements

### Setup & Authentication

- [x] **AUTH-01**: Premier lancement affiche un setup wizard pour creer le compte administrateur
- [x] **AUTH-02**: Utilisateur peut se connecter avec email et mot de passe (BFF cookie flow, JWT cote serveur, cookies httpOnly)
- [x] **AUTH-03**: Utilisateur peut se deconnecter depuis n'importe quelle page
- [x] **AUTH-04**: Session utilisateur persiste apres rafraichissement du navigateur
- [x] **AUTH-05**: Protection CSRF active sur tous les endpoints mutatifs

### Administration

- [ ] **ADMN-01**: Admin peut inviter de nouveaux utilisateurs (email d'invitation)
- [ ] **ADMN-02**: Admin peut gerer les droits des utilisateurs
- [ ] **ADMN-03**: Admin peut configurer les connexions Plaid (ajout, suppression, statut)
- [ ] **ADMN-04**: Admin peut voir le monitoring systeme (statut synchro, sante de l'app)

### Comptes Bancaires

- [x] **ACCT-01**: Utilisateur peut creer un compte bancaire personnel
- [x] **ACCT-02**: Utilisateur peut creer un compte bancaire commun (partage entre utilisateurs)
- [x] **ACCT-03**: Utilisateur peut voir la liste de ses comptes avec soldes
- [x] **ACCT-04**: Utilisateur peut modifier les informations d'un compte (nom, type)
- [x] **ACCT-05**: Utilisateur peut archiver un compte (masque sans supprimer les donnees)

### Controle d'Acces

- [x] **ACCS-01**: Chaque compte a des permissions par utilisateur (lecture/ecriture/admin)
- [x] **ACCS-02**: Utilisateur ne voit que les comptes auxquels il a acces
- [x] **ACCS-03**: Admin peut modifier les permissions d'acces aux comptes pour chaque utilisateur
- [x] **ACCS-04**: Le controle d'acces s'applique aux requetes d'agregation (dashboard, recherche)

### Transactions

- [ ] **TXNS-01**: Utilisateur peut saisir manuellement une transaction (montant, date, description, categorie, compte)
- [ ] **TXNS-02**: Utilisateur peut modifier une transaction saisie manuellement
- [ ] **TXNS-03**: Utilisateur peut supprimer une transaction saisie manuellement
- [ ] **TXNS-04**: Utilisateur peut creer des templates de transactions recurrentes (loyer, abonnements)
- [ ] **TXNS-05**: Utilisateur peut pointer manuellement une transaction (associer saisie manuelle a import Plaid)
- [ ] **TXNS-06**: Utilisateur peut splitter une transaction en plusieurs categories (split transactions)
- [ ] **TXNS-07**: Utilisateur peut rechercher et filtrer les transactions (date, montant, categorie, description)
- [ ] **TXNS-08**: Liste des transactions avec pagination

### Categorisation

- [x] **CATG-01**: Les transactions importees via Plaid arrivent avec les categories Plaid pre-remplies
- [x] **CATG-02**: Utilisateur peut modifier la categorie d'une transaction
- [x] **CATG-03**: Utilisateur peut creer des categories personnalisees
- [x] **CATG-04**: Les categories sont hierarchiques (categorie parente / sous-categorie)

### Import Bancaire (Plaid)

- [ ] **PLAD-01**: Admin peut connecter un compte bancaire via Plaid Link (SG, Banque Populaire)
- [ ] **PLAD-02**: Utilisateur peut declencher un import manuel des transactions
- [ ] **PLAD-03**: Import planifie automatique (batch, frequence configurable)
- [ ] **PLAD-04**: Import initial parametrable (profondeur d'historique)
- [ ] **PLAD-05**: Gestion correcte des transitions pending -> posted (delete + create, pas update)
- [ ] **PLAD-06**: Gestion du cycle de consentement PSD2 (renouvellement tous les 180 jours)
- [ ] **PLAD-07**: Interface abstraite pour le connecteur bancaire (Plaid interchangeable)

### Budgets Enveloppes

- [ ] **ENVL-01**: Utilisateur peut creer une enveloppe budgetaire sur un compte
- [ ] **ENVL-02**: Utilisateur peut allouer un montant mensuel a une enveloppe
- [ ] **ENVL-03**: Les depenses categorisees sont automatiquement imputees a l'enveloppe correspondante
- [ ] **ENVL-04**: Rollover parametrable par enveloppe (report automatique du solde ou remise a zero)
- [ ] **ENVL-05**: Indicateur visuel de depassement (rouge/jaune quand enveloppe depassee ou proche)
- [ ] **ENVL-06**: Utilisateur peut voir l'historique de consommation d'une enveloppe
- [ ] **ENVL-07**: Utilisateur peut modifier ou supprimer une enveloppe

### Dette Interne

- [ ] **DEBT-01**: Le systeme calcule automatiquement qui doit quoi a qui depuis les transactions sur comptes communs
- [ ] **DEBT-02**: Utilisateur peut voir le solde de dette interne avec chaque membre du foyer
- [ ] **DEBT-03**: Utilisateur peut enregistrer un remboursement (objectif = solde zero)
- [ ] **DEBT-04**: Historique long terme des dettes et remboursements

### Dashboard

- [ ] **DASH-01**: Utilisateur voit les soldes de tous ses comptes sur une vue consolidee
- [ ] **DASH-02**: Utilisateur voit l'etat de ses enveloppes (restant, consomme, pourcentage)
- [ ] **DASH-03**: Utilisateur voit des graphiques d'evolution (soldes et depenses dans le temps)
- [ ] **DASH-04**: Utilisateur voit les dernieres transactions tous comptes confondus

### Infrastructure

- [ ] **INFR-01**: Backup PostgreSQL automatise via pg_dump planifie
- [x] **INFR-02**: Docker Compose fonctionnel (Caddy + Spring Boot + PostgreSQL)
- [ ] **INFR-03**: PWA installable avec service worker actif
- [x] **INFR-04**: Linting : Checkstyle pour Java, ESLint pour Angular, execution locale (scripts) et CI
- [x] **INFR-05**: Formatage automatique : google-java-format pour Java, Prettier pour frontend, verification en CI
- [x] **INFR-06**: Analyse statique integree (SonarQube ou equivalent) avec quality gate locale et CI
- [x] **INFR-07**: Detection de code mort (Java + Angular) integree au pipeline CI
- [x] **INFR-08**: Couverture de tests enforcee avec seuils minimum (echec build si non atteint)
- [x] **INFR-09**: Scan de securite des dependances (vulnerabilites connues, OWASP dependency-check)
- [x] **INFR-10**: Pre-commit hooks (Husky/lefthook) executant lint, format, et checks avant chaque commit

## v2 Requirements

### Rapports

- **REPT-01**: Rapports de depenses par categorie sur periode configurable
- **REPT-02**: Rapport evolution patrimoine net (net worth)
- **REPT-03**: Comparaison depenses mois par mois / annee par annee

### Notifications

- **NOTF-01**: Notification in-app quand une enveloppe depasse un seuil
- **NOTF-02**: Notification push PWA pour alertes budget
- **NOTF-03**: Preferences de notification configurables par utilisateur

### Categorisation Avancee

- **CATG-05**: Regles de categorisation automatique (si libelle contient X -> categorie Y)
- **CATG-06**: Suggestions de categorie basees sur l'historique

### Ameliorations Sync

- **PLAD-08**: Sync temps reel via webhooks Plaid
- **PLAD-09**: Suggestion automatique de pointage (montant + date proches)

### Offline & Mobile

- **OFFL-01**: Mode offline-first PWA avec synchronisation
- **OFFL-02**: Experience mobile optimisee (gestes, navigation adaptee)

## Out of Scope

| Feature | Reason |
|---------|--------|
| App native iOS/Android | PWA couvre le besoin mobile, pas d'app store |
| Multi-devises | Comptes en euros uniquement, complexite enorme |
| Multi-foyers / mode SaaS | Self-hosted pour un seul foyer |
| Investissements / portefeuille | Domaine different, utiliser un outil dedie |
| Bill splitting externe | Hors foyer, utiliser Splitwise |
| Double-entry accounting | Pas necessaire pour le budgeting enveloppes |
| Enveloppes cross-account | Per-account en v1, evaluer en v2 selon usage |
| Categorisation ML | Necessite donnees d'entrainement, premature en v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 2 | Complete |
| AUTH-02 | Phase 2 | Complete |
| AUTH-03 | Phase 2 | Complete |
| AUTH-04 | Phase 2 | Complete |
| AUTH-05 | Phase 2 | Complete |
| ADMN-01 | Phase 8 | Pending |
| ADMN-02 | Phase 8 | Pending |
| ADMN-03 | Phase 7 | Pending |
| ADMN-04 | Phase 8 | Pending |
| ACCT-01 | Phase 3 | Complete |
| ACCT-02 | Phase 3 | Complete |
| ACCT-03 | Phase 3 | Complete |
| ACCT-04 | Phase 3 | Complete |
| ACCT-05 | Phase 3 | Complete |
| ACCS-01 | Phase 3 | Complete |
| ACCS-02 | Phase 3 | Complete |
| ACCS-03 | Phase 3 | Complete |
| ACCS-04 | Phase 3 | Complete |
| TXNS-01 | Phase 5 | Pending |
| TXNS-02 | Phase 5 | Pending |
| TXNS-03 | Phase 5 | Pending |
| TXNS-04 | Phase 5 | Pending |
| TXNS-05 | Phase 5 | Pending |
| TXNS-06 | Phase 5 | Pending |
| TXNS-07 | Phase 5 | Pending |
| TXNS-08 | Phase 5 | Pending |
| CATG-01 | Phase 4 | Complete |
| CATG-02 | Phase 4 | Complete |
| CATG-03 | Phase 4 | Complete |
| CATG-04 | Phase 4 | Complete |
| PLAD-01 | Phase 7 | Pending |
| PLAD-02 | Phase 7 | Pending |
| PLAD-03 | Phase 7 | Pending |
| PLAD-04 | Phase 7 | Pending |
| PLAD-05 | Phase 7 | Pending |
| PLAD-06 | Phase 7 | Pending |
| PLAD-07 | Phase 7 | Pending |
| ENVL-01 | Phase 6 | Pending |
| ENVL-02 | Phase 6 | Pending |
| ENVL-03 | Phase 6 | Pending |
| ENVL-04 | Phase 6 | Pending |
| ENVL-05 | Phase 6 | Pending |
| ENVL-06 | Phase 6 | Pending |
| ENVL-07 | Phase 6 | Pending |
| DEBT-01 | Phase 9 | Pending |
| DEBT-02 | Phase 9 | Pending |
| DEBT-03 | Phase 9 | Pending |
| DEBT-04 | Phase 9 | Pending |
| DASH-01 | Phase 10 | Pending |
| DASH-02 | Phase 10 | Pending |
| DASH-03 | Phase 10 | Pending |
| DASH-04 | Phase 10 | Pending |
| INFR-01 | Phase 10 | Pending |
| INFR-02 | Phase 1 | Complete |
| INFR-03 | Phase 10 | Pending |
| INFR-04 | Phase 1 | Complete |
| INFR-05 | Phase 1 | Complete |
| INFR-06 | Phase 1 | Complete |
| INFR-07 | Phase 1 | Complete |
| INFR-08 | Phase 1 | Complete |
| INFR-09 | Phase 1 | Complete |
| INFR-10 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 62 total
- Mapped to phases: 62
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after roadmap revision (added INFR-04 through INFR-10 quality gates)*
