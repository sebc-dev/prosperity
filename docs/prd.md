## 1. Objectifs et Contexte

### Objectifs

* **Transparence financiere :** Offrir au couple une vision claire et actualisee de leurs budgets, possibilites et restrictions.
* **Automatisation des dettes :** Eliminer les approximations sur "qui doit combien" grace au suivi automatise des remboursements.
* **Centralisation :** Remplacer completement le systeme actuel (apps bancaires + tableurs + notes mentales) par un outil unique.
* **Maitrise Technique & UX :** Servir de projet d'apprentissage pour maitriser Spring Boot moderne (Java 21+), Svelte 5/SvelteKit, et creer une PWA offline-first performante. Post-MVP : integration MCP pour analyses intelligentes.

### Contexte

Prosperity est une application web de gestion financiere auto-hebergee et open source, concue pour un couple souhaitant un controle total sur ses donnees. C'est un side project personnel, pas un produit commercial.

Les solutions existantes ne repondent pas au besoin specifique d'une gestion multi-utilisateurs collaborative pour des comptes personnels et communs, avec suivi integre des dettes internes entre conjoints.

### Problemes identifies avec les solutions existantes

* **Firefly III / Actual Budget** : Import bancaire complexe, configuration non-intuitive, gestion budgetaire trop rigide sans cycles mensuels clairs
* **Solutions SaaS (YNAB, etc.)** : Pas d'auto-hebergement, cout recurrent, donnees hebergees chez des tiers
* **Situation actuelle** : Previsions sur Excel, gestion des dettes a l'oral, aucun suivi budgetaire en temps reel

### Profils Utilisateurs

* **Utilisateur Principal** : Technophile, a l'aise avec interfaces complexes, responsable de la configuration et de l'administration
* **Utilisateur Secondaire** : Non-technophile, privilegie simplicite et clarte, utilisatrice finale quotidienne
* **Contrainte UX** : L'interface doit etre suffisamment simple pour etre adoptee par un utilisateur non-technique

## 2. Exigences

### Exigences Fonctionnelles

1. **FR1 : Gestion Multi-Utilisateurs Conjugale :**
   Le systeme gere deux utilisateurs avec des comptes personnels et partages :
   - **Admin** (utilisateur principal) : gestion des comptes, configuration Plaid, administration systeme
   - **Utilisateur standard** : acces aux comptes partages et a ses comptes personnels
   - **Comptes personnels** : visibles uniquement par le proprietaire
   - **Comptes partages** : les deux utilisateurs peuvent consulter et saisir des transactions

2. **FR2 : Importation Automatisee :** Le systeme doit permettre l'importation securisee et automatique des transactions bancaires via l'integration Plaid Link (banques francaises/europeennes supportees).

3. **FR3 : Gestion des Transactions (modele previsionnel + rapprochement) :**
   Le systeme gere deux types de transactions :
   - **Saisies (previsions)** : transactions saisies manuellement, potentiellement recurrentes (loyer, abonnements). Elles representent des depenses prevues et permettent de visualiser le budget restant avant que les operations bancaires ne soient importees.
   - **Importees (reelles)** : transactions provenant de Plaid Link, representant les operations bancaires effectives.
   - **Pointage (rapprochement)** : lorsqu'une transaction importee correspond a une saisie, l'utilisateur les associe. La saisie passe de "prevue" a "pointee". Les saisies non pointees restent visibles comme depenses attendues.
   - **Double solde** : chaque compte affiche un solde reel (banque) et un solde projete (reel + previsions non pointees).
   - Les utilisateurs doivent pouvoir saisir, categoriser et rapprocher les transactions.

4. **FR4 : Suivi des Dettes Internes :** Le systeme doit permettre d'enregistrer, suivre, calculer les soldes et suggerer des equilibrages pour les avances et remboursements entre les deux utilisateurs. Widget dashboard avec solde net visible en permanence.

5. **FR5 : Budgetisation :** Les utilisateurs doivent pouvoir definir et suivre des budgets mensuels par categorie de depenses, individuels et communs.

6. **FR6 : Tableau de Bord :** L'interface principale doit presenter une vue claire incluant les soldes des comptes (reel et projete avec previsions non pointees), l'etat des budgets avec indicateurs visuels, les dernieres transactions et le solde des dettes internes.

7. **FR7 : Saisie Mobile Offline-First :** L'application doit fonctionner comme une PWA permettant la saisie rapide de transactions en mode hors-ligne, avec synchronisation differee.

### Exigences Non-Fonctionnelles

1. **NFR1 : Auto-Hebergement :** L'application complete doit etre deployable sur une infrastructure privee via Docker et docker-compose.

2. **NFR2 : Performance API :** Temps de reponse API < 200ms pour 95% des requetes.

3. **NFR3 : Performance Frontend :** Chargement initial < 2s sur connexion 4G.

4. **NFR4 : Qualite et Securite — Local-First :**
   La majorite des verifications se fait en local avant chaque push. La CI est un filet de securite pour les analyses lourdes ou de formatage.

   **Pre-commit hooks :**
   * Backend : Maven Enforcer (empeche de commit du code qui ne compile pas)
   * Frontend : husky + lint-staged (formatage automatique avant chaque commit)

   **En local (avant chaque push) :**
   * Tests unitaires et d'integration (JUnit 5, Testcontainers)
   * Tests frontend (vitest, @testing-library/svelte, axe-core)
   * ArchUnit : enforcement des regles d'architecture dans les tests (isolation vertical slice, conventions d'import)
   * SpotBugs : detection de bugs et patterns dangereux dans le bytecode Java
   * PIT mutation testing : verification de la qualite reelle des tests (mutations non tuees = tests faibles)
   * Snyk : vulnerabilites des dependances (backend + frontend)
   * Trivy : scan de vulnerabilites des images Docker et du filesystem
   * `npm audit` pour le frontend

   **En CI (GitHub Actions, sur chaque push) :**
   * Build et formatage/lint (Checkstyle, ESLint, Prettier, svelte-check)
   * SpotBugs (verification que le build ne contient pas de bugs detectables)
   * ArchUnit (verification des regles d'architecture)
   * SonarQube avec quality gate bloquant :
     - Coverage on new code > 80%
     - Duplicated lines on new code < 3%
     - Maintainability rating (new code) : A
     - Reliability rating (new code) : A
     - Security rating (new code) : A
     - Security hotspots reviewed : 100%
   * Build des images Docker sur merge dans main

   **En CI (schedule hebdomadaire) :**
   * OWASP Dependency-Check (scan CVE complet — trop long pour chaque push)
   * Maven License Plugin : verification des licences des dependances (compatibilite open source)

5. **NFR5 : Qualite du Code :** Couverture de tests > 80%, mutation testing avec PIT (objectif : > 70% de mutations tuees), architecture enforcee par ArchUnit, zero duplication > 3% sur le nouveau code.

6. **NFR6 : Securite :** HTTPS obligatoire, chiffrement des tokens Plaid au repos (AES-256), mots de passe bcryptes, headers de securite (CSP, HSTS), conformite OWASP Top 10:2025.

7. **NFR7 : Gestion des Conflits de Synchronisation :**
   Detection et resolution des conflits lors de la synchronisation offline/online :
   * Detection automatique des doublons potentiels (meme montant +/- 10% dans une fenetre de 5 min)
   * Interface simple de resolution
   * Option "Ce sont deux transactions differentes"
   * Annulation des resolutions pendant 24h

8. **NFR8 : Observabilite :**
   * Logs structures avec rotation automatique
   * Health check endpoint (Spring Boot Actuator)
   * Metriques essentielles : temps de reponse, erreurs, imports Plaid

## 3. Conception de l'Interface Utilisateur

### Vision UX

L'interface privilegie la clarte et la simplicite, adaptee a un utilisateur non-technique. Comprehension immediate de la situation financiere, saisie rapide et intuitive sur mobile. L'experience doit inspirer confiance sans intimider.

### Accessibilite

Le projet vise WCAG 2.2 niveau AA :

* Navigation clavier complete
* Contrastes suffisants (4.5:1 texte, 3:1 elements larges)
* Zones tactiles minimum 44x44px
* Indicateurs non uniquement colores
* Audits automatiques (axe-core) integres en CI
* Tests manuels reguliers avec l'utilisatrice cible

### Paradigmes d'Interaction

* **Tableau de bord informatif :** Visualisations claires, interactions limitees aux actions essentielles
* **Saisie ultra-rapide ("Quick-add")** : Objectif <= 3 taps pour une depense basique (montant + categorie)
* **Mobile-First adaptatif :** Mobile = saisie + consultation / Desktop = configuration + analyse

### Ecrans Principaux

* Authentification (Login)
* Tableau de Bord Principal
* Formulaire de Saisie / Edition de Transaction (+ quick-add mobile)
* Vue Detaillee d'un Compte (historique des transactions)
* Gestion des Budgets (creation et suivi)
* Suivi des Dettes Internes (avec option "regler")
* Parametres (Profil, comptes Plaid)
* Resolution des Conflits de Synchronisation

### Repartition Mobile/Desktop

* **Mobile (tous)** : Dashboard, saisie rapide, consultation transactions
* **Desktop (admin)** : Config Plaid, creation budgets, resolution conflits, analyses

## 4. Hypotheses Techniques

### Structure du Depot : Monorepo

Un monorepo contenant le backend et le frontend. Facilite la gestion des dependances et le developpement en solo.

### Architecture Backend : Vertical Slice avec Domain Kernel

Organisation par fonctionnalite metier (account, transaction, debt, budget) avec un kernel partage pour les preoccupations transversales (securite, persistence, configuration). Chaque feature contient son controller, service, repository et DTOs. Cf. `docs/architecture.md` pour le detail.

### Stack Technologique

* **Backend :** Java 21 LTS avec Spring Boot 3.3+, Spring Security (JWT + Refresh Tokens), Spring Data JPA, PostgreSQL, Liquibase
* **Frontend :** Svelte 5 + SvelteKit 2, TypeScript, Tailwind CSS, PWA avec Service Workers et IndexedDB
* **Infrastructure :** Docker & docker-compose, Caddy (reverse proxy existant), PostgreSQL
* **Integration bancaire :** Plaid Link (banques FR/EU)
* **Monitoring :** Logs structures (Logback) + Spring Boot Actuator

### Conventions Java 21

Le projet utilise directement les features Java 21 (pas de migration depuis Java 8) :
* Records pour tous les DTOs, events, value objects
* Sealed classes/interfaces pour les types de domaine
* Pattern matching (instanceof, switch)
* Virtual threads pour les operations I/O
* Switch expressions, text blocks, var

### Strategie de Tests

Pyramide de tests equilibree :
* **Unitaires** (JUnit 5, Mockito) : logique metier des services
* **Integration** (Testcontainers, @SpringBootTest) : repositories et endpoints
* **Composants frontend** (vitest, @testing-library/svelte, axe-core) : UI et accessibilite
* **E2E** (Playwright) : parcours critiques (login, saisie, dashboard)

## 5. Epics MVP

### Epic 1 : Infrastructure et Fondations

**Objectif :** Etablir la fondation technique du projet.

#### Story 1.1 : Initialisation du Projet

**En tant que** developpeur, **je veux** une structure de projet fonctionnelle, **afin de** commencer le developpement.

**Criteres d'Acceptation :**

1. Monorepo avec backend Spring Boot 3.3+ / Java 21 et frontend SvelteKit 2
2. Configuration PostgreSQL avec Liquibase pour les migrations
3. Docker multi-stage builds (backend + frontend)
4. `docker-compose.yml` avec profils dev/prod
5. `.env.example` avec les variables d'environnement documentees
6. Architecture Vertical Slice en place (shared/ + features vides)

#### Story 1.2 : Securite de Base

**En tant que** utilisateur, **je veux** que mes donnees soient protegees, **afin de** utiliser l'application en confiance.

**Criteres d'Acceptation :**

1. Spring Security avec JWT (15min) + Refresh Tokens avec rotation automatique
2. Headers de securite : CSP, HSTS, X-Frame-Options, X-Content-Type-Options
3. Rate limiting basique
4. Configuration CORS restrictive
5. Mots de passe bcryptes (12 rounds)

#### Story 1.3 : Pipeline CI/CD

**En tant que** developpeur, **je veux** automatiser les tests, **afin de** maintenir la qualite du code.

**Criteres d'Acceptation :**

1. GitHub Actions configure
2. Build, formatage (Checkstyle) et lint backend sur chaque push
3. Build, lint (ESLint, Prettier) et svelte-check frontend sur chaque push
4. SpotBugs sur chaque push
5. SonarQube avec quality gate bloquant sur chaque push
6. Build des images Docker sur merge dans main
7. OWASP Dependency-Check en schedule hebdomadaire (cron)

#### Story 1.4 : Sauvegarde et Monitoring

**En tant que** administrateur, **je veux** proteger mes donnees et surveiller l'application.

**Criteres d'Acceptation :**

1. Backup PostgreSQL quotidien (pg_dump) avec chiffrement GPG
2. Retention : 7 jours local, 30 jours distant
3. Spring Boot Actuator avec health endpoint
4. Logs structures avec rotation quotidienne

### Epic 2 : Authentification et Gestion des Comptes

**Objectif :** Permettre aux deux utilisateurs de se connecter et gerer leurs comptes bancaires.

#### Story 2.1 : Authentification

**En tant que** utilisateur, **je veux** me connecter de maniere securisee.

**Criteres d'Acceptation :**

1. Deux roles : Admin et Standard
2. Login avec identifiant (email) et mot de passe
3. Sessions persistantes via JWT
4. Page de login accessible et responsive

#### Story 2.2 : Gestion des Comptes Bancaires

**En tant que** utilisateur, **je veux** gerer mes comptes bancaires, **afin de** organiser mes finances.

**Criteres d'Acceptation :**

1. CRUD comptes bancaires avec type : Personnel ou Partage
2. Comptes personnels visibles uniquement par le proprietaire
3. Comptes partages accessibles aux deux utilisateurs
4. Badge visuel pour distinguer personnel/partage

#### Story 2.3 : Profil et Preferences

**En tant que** utilisateur, **je veux** personnaliser mon experience.

**Criteres d'Acceptation :**

1. Page profil avec informations personnelles
2. Preferences : devise par defaut, categories favorites pour quick-add
3. Theme clair/sombre avec detection systeme

### Epic 3 : Transactions et Integration Plaid

**Objectif :** Gerer les transactions manuelles et automatiser l'import bancaire.

#### Story 3.1 : Saisie des Transactions (Previsions)

**En tant que** utilisateur, **je veux** saisir mes depenses prevues manuellement, **afin de** visualiser mon budget restant avant que les operations bancaires ne soient importees.

**Criteres d'Acceptation :**

1. Formulaire de saisie : montant, description, date, categorie, compte
2. Edition et suppression des saisies
3. Categorisation manuelle
4. Possibilite de marquer une saisie comme recurrente (mensuelle) pour les depenses fixes (loyer, abonnements)
5. Generation automatique des saisies recurrentes en debut de mois
6. Les saisies non pointees apparaissent comme depenses prevues dans le solde projete
7. Historique des transactions avec filtres (date, categorie, compte, statut : prevue/pointee/importee)

#### Story 3.2 : Integration Plaid et Pointage

**En tant que** utilisateur, **je veux** connecter mes comptes bancaires et rapprocher les imports avec mes saisies, **afin de** maintenir une vue financiere fiable.

**Criteres d'Acceptation :**

1. Configuration Plaid par l'admin (cles API)
2. Connexion de comptes bancaires via Plaid Link
3. Import automatique des transactions (type "importee")
4. Pointage : l'utilisateur peut associer une transaction importee a une saisie existante (la saisie passe de "prevue" a "pointee")
5. Suggestion automatique de rapprochement (meme montant +/- tolerance, dates proches)
6. Les transactions importees sans saisie correspondante restent autonomes
7. Chiffrement AES-256 des tokens Plaid au repos
8. Gestion des erreurs : token expire, institution indisponible, mode degrade (saisie manuelle)

#### Story 3.3 : Saisie Rapide Mobile

**En tant que** utilisateur mobile, **je veux** saisir une depense en 3 taps maximum.

**Criteres d'Acceptation :**

1. Bouton flottant "+" toujours visible
2. Formulaire en 3 etapes : montant, categorie (6 favorites + "Autre"), validation
3. Compte par defaut pre-selectionne

### Epic 4 : Budgets et Dettes

**Objectif :** Implementer la budgetisation et le suivi des dettes internes.

#### Story 4.1 : Budgets Mensuels

**En tant que** couple, **nous voulons** definir et suivre nos budgets.

**Criteres d'Acceptation :**

1. Creation de budgets par categorie avec montant mensuel
2. Budgets individuels et communs
3. Deux modes de budget : "enveloppe" (depenser jusqu'a epuisement) et "objectif" (cible d'epargne)
4. Templates de budgets preetablis (courses, loisirs, transport, etc.)
5. Suivi de la consommation avec jauges visuelles
6. Alertes progressives : 75%, 90%, 100% du budget
7. Analyse des ecarts : comparaison budget prevu vs reel avec suggestions d'ajustement

#### Story 4.2 : Suivi des Dettes Internes

**En tant que** couple, **nous voulons** savoir qui doit combien a qui.

**Criteres d'Acceptation :**

1. Marquage des transactions comme avance ("Paye par X pour le couple")
2. Calcul automatique du solde net entre les deux utilisateurs
3. Suggestions d'equilibrage (virement unique)
4. Widget dashboard avec solde net visible en permanence
5. Historique des avances et remboursements

### Epic 5 : Dashboard et PWA

**Objectif :** Creer le tableau de bord principal et les capacites offline.

#### Story 5.1 : Tableau de Bord

**En tant que** utilisateur, **je veux** voir ma situation financiere d'un coup d'oeil.

**Criteres d'Acceptation :**

1. Soldes des comptes (reel et projete avec previsions non pointees)
2. Etat des budgets avec jauges visuelles
3. 5 dernieres transactions
4. Solde des dettes internes avec action rapide
5. Responsive : mobile et desktop

#### Story 5.2 : PWA Offline-First

**En tant que** utilisateur mobile, **je veux** utiliser l'app sans connexion.

**Criteres d'Acceptation :**

1. Service Worker avec cache-first pour assets, network-first pour API
2. IndexedDB pour stockage local des transactions
3. Queue de synchronisation avec retry
4. Indicateur visuel online/offline
5. Badge sur transactions non synchronisees
6. Synchronisation en arriere-plan (Background Sync API)

#### Story 5.3 : Resolution des Conflits

**En tant que** couple, **nous voulons** eviter les doublons lors de saisies simultanees.

**Criteres d'Acceptation :**

1. Detection automatique : meme montant +/- 10% dans une fenetre de 5 min
2. Interface de resolution : vue cote a cote, options "Garder celle-ci" / "Garder l'autre" / "Ce sont 2 transactions differentes"
3. Historique des resolutions avec undo 24h

## 6. Post-MVP

### Phase 2 : IA et Analyses

* **Serveur MCP :** Analyses automatisees des depenses, detection de patterns, conseils budgetaires
* **Categorisation IA :** Auto-categorisation des transactions basee sur l'historique
* **Rapports intelligents :** Insights financiers mensuels personnalises

### Phase 3 : Sophistication

* **Notifications :** Rappels de dettes, alertes budgetaires par email et push PWA
* **Projections :** Previsions simples basees sur l'historique (3-6 mois)
* **Export :** PDF pour releves, CSV/JSON pour les donnees completes
* **Graphiques avances :** Evolution des soldes, repartition des depenses, tendances

## 7. Securite et Donnees

### Securite

* HTTPS obligatoire (Caddy + Let's Encrypt)
* JWT + Refresh Tokens avec rotation automatique
* BCrypt 12 rounds pour les mots de passe
* AES-256 pour les tokens Plaid au repos
* Headers : CSP, HSTS, X-Frame-Options
* Rate limiting basique
* Conformite OWASP Top 10:2025 — les 10 risques :
  * A01 : Broken Access Control — permissions par compte, @PreAuthorize
  * A02 : Security Misconfiguration — headers securises, CORS restrictif, config externalisee
  * A03 : Vulnerable and Outdated Components — Snyk + Dependency-Check en CI
  * A04 : Cryptographic Failures — AES-256 tokens, BCrypt passwords, HTTPS
  * A05 : Injection — requetes parametrees JPA, Bean Validation, echappement natif Svelte
  * A06 : Insecure Design — architecture par feature avec isolation, validation metier dans les services
  * A07 : Software Supply Chain Failures — lockfiles, scan des dependances, images Docker verifiees
  * A08 : Identification and Authentication Failures — JWT court, rotation refresh tokens, rate limiting login
  * A09 : Security Logging and Monitoring Failures — audit log, logs structures, health checks
  * A10 : Mishandling of Exceptional Conditions — GlobalExceptionHandler, erreurs metier typees, pas de stack traces en production

### Outils de Qualite et Securite

Le code etant genere par IA (Claude Code), des garde-fous automatises sont essentiels :

**Analyse statique et qualite :**
* **SonarQube** : analyse statique, dette technique, couverture, quality gate — CI
* **SpotBugs** : detection de bugs dans le bytecode Java — local + CI
* **PIT Mutation Testing** : verifie que les tests detectent vraiment les regressions — local
* **ArchUnit** : enforcement des regles d'architecture (isolation features, conventions d'import) — local + CI
* **Checkstyle** : conventions de style Java — CI
* **ESLint + Prettier** : formatage et linting frontend — CI (+ pre-commit via husky)
* **svelte-check** : validation TypeScript complete — CI

**Securite :**
* **Snyk** : vulnerabilites des dependances (Maven + npm) — local
* **Trivy** : scan des images Docker et du filesystem pour CVE — local
* **OWASP Dependency-Check** : scan CVE exhaustif des dependances Java — CI hebdomadaire

**Architecture (ArchUnit) — regles enforcees :**
* Les features (`account/`, `transaction/`, etc.) ne s'importent pas entre elles
* Seul `shared/` est importable par les features
* Les controllers n'appellent jamais les repositories directement
* Les records DTO n'importent pas JPA
* Les services ne dependent pas des controllers

**Pre-commit :**
* **husky + lint-staged** : formatage automatique frontend avant chaque commit
* **Maven Enforcer** : verification de compilation backend

**Licences :**
* **Maven License Plugin** : verification hebdomadaire de compatibilite des licences (open source)

**Accessibilite :**
* **axe-core** : audit accessibilite automatique — local (vitest)

### Protection des Donnees

* Donnees hebergees exclusivement sur infrastructure privee
* Export complet des donnees (JSON/CSV) a tout moment
* Suppression definitive possible
* Audit log : connexions et modifications sensibles
* Retention : 5 ans transactions, 1 an logs
