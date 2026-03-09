## Énoncé du Problème

En tant que développeur expérimenté, j'ai testé la plupart des solutions de gestion financière existantes et aucune ne correspond à ma vision d'un outil familial moderne et maîtrisé. Le problème se décompose en plusieurs points clés :

- **Manque de contrôle de l'infrastructure** : Les solutions SaaS m'obligent à confier mes données financières sensibles à des tiers, sans possibilité de maîtriser l'hébergement, les sauvegardes ou les mises à jour.
- **Gestion multi-utilisateurs inadaptée** : Les solutions existantes soit séparent complètement les utilisateurs (Firefly III), soit offrent un support expérimental (Actual Budget), soit se contentent de partager un accès unique. Aucune ne permet une vraie collaboration entre conjoints sur comptes personnels et partagés.
- **Absence de suivi des dettes internes** : Le suivi des avances et remboursements entre conjoints reste une tâche manuelle fastidieuse. Les solutions spécialisées (Splitwise) ne s'intègrent pas dans l'écosystème de gestion financière global.
- **Interface et UX datées** : Les solutions open-source privilégient la fonctionnalité sur l'expérience utilisateur. Les solutions commerciales ont de bonnes UX mais sans possibilité de les adapter à mes besoins spécifiques.
- **Manque d'intégration IA moderne** : Aucune solution ne propose d'analyse intelligente des dépenses ou de conseils personnalisés via des technologies modernes comme les serveurs MCP.

## Solution Proposée

Prosperity sera une application web auto-hébergée moderne, conçue initialement pour un couple partageant finances personnelles et communes. La proposition de valeur repose sur quatre piliers :

- **Auto-Hébergement avec Commodité Moderne** : Application open-source déployable sur infrastructure privée (Docker/Debian), combinant le contrôle des données avec l'automatisation moderne via l'intégration Plaid Link pour l'import sécurisé des transactions bancaires.
    
- **Collaboration Conjugale Native** : Système multi-utilisateurs conçu dès le départ pour la collaboration entre conjoints, permettant la gestion simultanée de comptes personnels et partagés avec visibilité configurable.
    
- **Suivi Intégré des Dettes Internes** : Fonctionnalité native pour enregistrer, suivre et équilibrer automatiquement les avances et remboursements entre conjoints, intégrée directement dans le dashboard principal avec notifications et rappels.
    
- **Expérience Utilisateur et IA Modernes** : Interface Svelte 5 contemporaine optimisée pour les tableaux de bord financiers, avec saisie mobile via PWA offline-first. Intégration d'un serveur MCP pour l'analyse intelligente des dépenses, conseils budgétaires personnalisés et rapports automatisés.
    

## Utilisateurs Cibles

L'application est conçue pour un usage conjugal privé, avec deux utilisateurs principaux partageant la responsabilité financière.

### Utilisateur Principal : "Le Couple Technophile"

- **Profil** : Couple avec compétences techniques suffisantes pour gérer un déploiement Docker et soucieux de contrôler leurs données financières. Ils gèrent à la fois des comptes personnels et des comptes communs.
- **Comportements Actuels** : Utilisent probablement des outils séparés (app bancaire + feuilles de calcul + notes mentales) pour suivre qui doit quoi à qui lors des dépenses communes.
- **Besoins et Frustrations** : Besoin d'une vue consolidée de leur situation financière commune et personnelle. Frustrés par les solutions SaaS qui ne permettent pas de customisation et par les solutions open-source aux interfaces datées.
- **Objectifs** : Automatiser le suivi financier, éliminer les approximations sur les dettes internes, disposer d'analyses intelligentes de leurs habitudes de dépenses, maintenir le contrôle de leurs données.

### Contexte Technique : "Le Développeur-Utilisateur"

- **Profil** : Développeur expérimenté utilisant ce projet comme terrain d'apprentissage pour Java/Spring moderne, Svelte 5/SvelteKit, et expérimentation MCP/IA.
- **Objectifs Techniques** : Mise en pratique de Spring Boot, architecture clean, intégration de technologies émergentes (MCP), optimisation UX avec focus sur les dashboards financiers. Montée en compétence sur Svelte 5 (runes, réactivité fine-grained) et SvelteKit 2 (routing, data loading, SSR/SPA).

Cette approche élimine la complexité des rôles granulaires familiaux au profit d'un focus sur la collaboration conjugale et l'excellence technique.

## Analyse Concurrentielle

### Solutions Existantes Évaluées

**Solutions Open-Source Testées :**

- **Firefly III** : Excellente fonctionnalité, mais gestion mono-utilisateur stricte. Interface fonctionnelle mais datée.
- **Actual Budget** : Support multi-utilisateurs expérimental, architecture moderne mais écosystème limité.
- **GNUCash** : Puissant mais complexité excessive, interface desktop inadaptée à l'usage mobile.

**Solutions SaaS Commerciales :**

- **YNAB** : Excellente UX et philosophie budgétaire, mais données hébergées et prix élevé.
- **Mint/Personal Capital** : Intégrations nombreuses mais fermeture programmée, aucun contrôle des données.
- **Splitwise** : Parfait pour les dettes mais n'intègre pas la gestion financière globale.

**Lacunes Identifiées :** Aucune solution ne combine auto-hébergement, collaboration conjugale native, suivi des dettes internes et technologies modernes (IA/MCP) dans une interface contemporaine.

## Architecture Technique

### Stack Technologique

**Backend :**

- Java 21+ avec Spring Boot 3.3+
- Spring Security pour l'authentification
- Spring Data JPA avec PostgreSQL
- Architecture Vertical Slice avec Domain Kernel (organisation par feature métier)
- API REST avec validation Bean Validation

**Frontend :**

- Svelte 5 avec SvelteKit 2 et TypeScript
- Runes Svelte 5 ($state, $derived, $effect) pour la réactivité fine-grained
- Fonctions load SvelteKit pour le data fetching côté serveur et client
- Tailwind CSS pour le styling
- SvelteKit avec adapter-node, déployé comme container Node dédié derrière Caddy
- PWA avec Service Workers natifs SvelteKit et IndexedDB

**Infrastructure :**

- Docker & docker-compose pour le déploiement
- PostgreSQL pour la persistance
- Redis pour le cache (optionnel post-MVP, si les métriques l'exigent)
- Caddy pour le reverse proxy et SSL

**Intégrations :**

- Plaid Link pour l'import bancaire automatisé
- Serveur MCP pour les analyses IA (Phase 2)

### Architecture Frontend SvelteKit

Le frontend SvelteKit sera déployé via `adapter-node`, produisant un serveur Node dédié dans son propre container Docker. Caddy (déjà en place sur le serveur) sert de reverse proxy avec HTTPS automatique. SvelteKit gère le routing basé fichiers, les fonctions `load` pour le data fetching, et les form actions pour les mutations côté serveur (progressive enhancement). Spring Boot reste la source de vérité pour toutes les données via son API REST.

Les runes Svelte 5 assureront une réactivité fine-grained sans virtual DOM, ce qui est particulièrement adapté aux dashboards financiers avec de nombreuses valeurs dynamiques.

### Modèle de Données Simplifié

**Entités Principales :**

- **Users** : Gestion des comptes conjugaux (2 utilisateurs)
- **Accounts** : Comptes bancaires personnels et partagés
- **Transactions** : Deux types — saisies (prévisions manuelles, potentiellement récurrentes) et importées (Plaid). Rapprochement (pointage) entre saisie et importée.
- **RecurrenceRules** : Règles de récurrence pour générer automatiquement les saisies périodiques (loyer, abonnements)
- **Categories** : Catégorisation des dépenses
- **Budgets** : Budgets mensuels par catégorie
- **InternalDebts** : Suivi des avances entre conjoints

## Objectifs et Métriques de Succès

#### Objectifs d'Apprentissage Technique

- **Maîtriser Spring Boot moderne :** Mise en pratique de Java 21/25, Spring Security, Spring Data JPA, architecture layered clean
- **Maîtriser Svelte 5 et SvelteKit 2 :** Apprentissage des runes ($state, $derived, $effect, $props), composants Svelte 5, routing SvelteKit, fonctions load, gestion d'erreurs, et patterns d'état avancés (stores, context)
- **Implémenter un serveur MCP fonctionnel :** Intégration réussie pour l'analyse IA des dépenses et conseils budgétaires automatisés
- **Créer une PWA offline-first performante :** Service Workers SvelteKit, IndexedDB, synchronisation différée, UX mobile fluide
- **Optimiser l'utilisation de l'IA générative :** Trouver l'équilibre optimal entre code généré et maîtrise manuelle du développement

#### Success Criteria Techniques

- **Performance :** Temps de réponse API <200ms, chargement initial <2s (Svelte 5 produit des bundles significativement plus légers qu'un équivalent React, facilitant cet objectif)
- **Infrastructure :** Pipeline CI/CD opérationnel, déploiement Docker reproductible
- **Qualité Code :** Couverture de tests maximale, architecture maintenable, code review IA systématique
- **Intégrations :** Plaid Link fonctionnel, serveur MCP opérationnel, PWA offline sans perte de données

#### Objectifs Personnels d'Usage

Le succès pour notre couple sera atteint quand :

- **Transparence financière :** Ma compagne et moi disposons d'une vision claire et actualisée de nos budgets, possibilités et restrictions
- **Automatisation des dettes :** Élimination des approximations et disputes sur "qui doit combien" grâce au suivi automatisé des remboursements
- **Abandon des outils actuels :** Remplacement complet de notre système actuel (apps bancaires + tableurs + notes mentales)

#### Métriques de Réussite

- **Adoption personnelle :** Utilisation quotidienne sur 3 mois consécutifs
- **Précision financière :** 100% des dépenses tracées et catégorisées
- **Harmonie conjugale :** Zéro dispute liée aux remboursements pendant 6 mois
- **Excellence technique :** Déploiement en production stable, monitoring opérationnel, sauvegardes automatisées

## Périmètre MVP

#### Fonctionnalités Principales

- **Système Multi-Utilisateurs Conjugal :**
    - Gestion de 2 utilisateurs avec accès aux comptes personnels et partagés
    - Permissions configurables par compte
- **Gestion des Transactions (modèle prévisionnel + rapprochement) :**
    - Deux types de transactions : **saisies** (prévisions manuelles, potentiellement récurrentes) et **importées** (réelles, via Plaid Link)
    - Saisie manuelle en avance pour prévoir les dépenses et visualiser le reste disponible
    - Transactions récurrentes (loyer, abonnements) générées automatiquement chaque mois
    - Importation automatique via Plaid Link
    - Pointage (rapprochement) : une transaction importée est associée à sa saisie correspondante
    - Les saisies non pointées restent visibles comme dépenses prévues
    - Double affichage des soldes : réel (banque) et projeté (réel + prévisions non pointées)
    - Catégorisation manuelle des transactions
- **Suivi des Dettes Internes :**
    - Enregistrement et suivi des avances entre conjoints
    - Calcul automatique des soldes nets
    - Suggestions d'équilibrage
- **Budgétisation :**
    - Définition et suivi de budgets mensuels par catégorie
- **Dashboard Complexe :**
    - Soldes des comptes avec jauges visuelles
    - État des budgets (dépensé vs alloué vs restant)
    - Transactions récentes avec statuts
    - Soldes des dettes internes
- **PWA Mobile Offline-First :**
    - Saisie rapide des transactions
    - Synchronisation différée via Service Workers SvelteKit
- **Infrastructure de Déploiement :**
    - Stack complète déployable via Docker/docker-compose

#### Hors Périmètre pour le MVP

- Intégration MCP/IA (V2 prioritaire)
- Projections financières complexes
- Notifications/rappels automatisés (push, email). Note : les alertes visuelles in-app pour les budgets (75%, 90%, 100%) sont incluses dans le MVP.

## Planning et Feuille de Route

### Phase MVP

**Infrastructure & Architecture**

- Setup projet Spring Boot + SvelteKit (monorepo ou workspaces)
- Configuration Docker/docker-compose (build SvelteKit statique + Spring Boot)
- Pipeline CI/CD basique
- Modèle de données PostgreSQL

**Authentification & Utilisateurs**

- Système d'authentification Spring Security
- Gestion des comptes conjugaux
- Interface de connexion/profil en Svelte 5

**Gestion des Comptes & Transactions**

- CRUD comptes bancaires
- Importation Plaid Link
- Saisie manuelle des transactions

**Suivi des Dettes & Budgets**

- Système de dettes internes
- Budgétisation par catégorie
- Calculs automatiques des soldes

**Dashboard Principal**

- Interface Svelte 5 du dashboard avec composants réactifs (runes)
- Visualisations des données financières (Layerchart ou Chart.js)
- UX responsive desktop/mobile

**PWA & Finalisation**

- Service Workers SvelteKit et mode offline
- Tests (Vitest pour les composants Svelte, Playwright pour l'E2E)
- Documentation de déploiement

### Phase 2 : IA & Analyses

**Intégration MCP :** Serveur MCP fonctionnel, analyses automatisées **Catégorisation IA :** Auto-catégorisation des transactions **Rapports Intelligents :** Insights financiers personnalisés

## Évaluation des Risques

### Risques Techniques

**Complexité de l'intégration Plaid :**

- _Impact_ : Moyen - _Probabilité_ : Faible
- _Mitigation_ : Documentation extensive, environnement sandbox, fallback saisie manuelle

**Performance PWA offline-first :**

- _Impact_ : Élevé - _Probabilité_ : Moyen
- _Mitigation_ : Prototypage early, tests sur vraies conditions réseau, architecture de sync robuste. SvelteKit offre un support natif des Service Workers via `src/service-worker.ts` facilitant l'implémentation.

**Courbe d'apprentissage Svelte 5 / SvelteKit :**

- _Impact_ : Moyen - _Probabilité_ : Moyen
- _Mitigation_ : Knowledge base Svelte 5/SvelteKit déjà constituée pour Claude Code, documentation officielle excellente, migration progressive des concepts connus (Vue.js). Les runes Svelte 5 introduisent un modèle mental différent mais la surface d'API est réduite comparée à React.

**Courbe d'apprentissage Spring moderne :**

- _Impact_ : Moyen - _Probabilité_ : Élevé
- _Mitigation_ : Formation continue, code reviews IA, architecture simple au départ

### Risques Produit

**Abandon suite à complexité excessive :**

- _Impact_ : Critique - _Probabilité_ : Moyen
- _Mitigation_ : MVP ultra-focalisé, validation continue avec ma compagne, itérations courtes

**Non-adoption par ma compagne :**

- _Impact_ : Élevé - _Probabilité_ : Faible
- _Mitigation_ : Implication dans la conception UX, formation progressive, transition douce

## Considérations de Sécurité et Confidentialité

### Sécurité des Données Financières

**Chiffrement :** Toutes les données sensibles chiffrées en base (AES-256) **Transport :** HTTPS obligatoire, certificats Let's Encrypt automatisés **Authentification :** Passwords bcryptés, sessions sécurisées, 2FA optionnel

### Privacy by Design

**Principe de Minimisation :** Collecte uniquement des données nécessaires au fonctionnement **Contrôle Utilisateur :** Export/suppression complète des données à tout moment **Hébergement Privé :** Aucune donnée ne quitte l'infrastructure personnelle

### Intégrations Externes

**Plaid Security :** Utilisation exclusive des tokens d'accès, aucun stockage de credentials bancaires **Audit Logs :** Traçabilité complète des accès et modifications de données sensibles

## Exigences Non-Fonctionnelles

### Performance

- **Temps de Réponse API :** <200ms pour 95% des requêtes
- **Chargement Initial :** <2s sur connexion 4G (facilité par les bundles légers de Svelte 5, pas de virtual DOM)
- **Synchronisation Offline :** <5s après reconnexion réseau

### Scalabilité

- **Utilisateurs Concurrents :** 2 (couple), architecture pensée pour 10 max
- **Volume de Données :** 50k+ transactions sur 5 ans sans dégradation
- **Déploiement :** Single-node suffisant, optimisation mémoire prioritaire

### Disponibilité

- **Uptime Cible :** 99% sur environnement personnel
- **Recovery Time :** <1h avec sauvegardes automatisées quotidiennes
- **Mode Dégradé :** PWA fonctionnelle même si backend indisponible

### Maintenabilité

- **Documentation :** README complet, documentation API, guides de déploiement
- **Tests :** Couverture >80%, tests unitaires Vitest, tests E2E Playwright
- **Monitoring :** Logs structurés, métriques applicatives, alertes proactives

## Exigences en Ressources

### Développement

**Outils & Services :**

- Plaid API (plan développeur gratuit puis ~$0.60/mois par compte lié)
- Serveur personnel existant (coût marginal nul)
- Nom de domaine et certificats (coût marginal)

### Infrastructure

**Ressources Serveur Minimales :**

- 2GB RAM, 20GB stockage, 1 vCPU
- PostgreSQL + Redis + application conteneurisées
- Sauvegardes automatisées (script rsync/rclone)

**Scalabilité :** Architecture pensée pour fonctionner sur Raspberry Pi 4 si besoin de réduction de coûts

## Vision Post-MVP

### Phase 2 : Intégration IA et Analyses Avancées

Après validation du MVP, la priorité sera l'intégration des technologies d'analyse intelligente qui constituent un objectif d'apprentissage majeur :

- **Serveur MCP Opérationnel :** Mise en place d'analyses automatisées des dépenses, détection de patterns, conseils budgétaires personnalisés basés sur l'historique
- **Catégorisation Automatique :** Utilisation de l'IA pour proposer automatiquement des catégories basées sur les descriptions de transactions
- **Rapports Intelligents :** Génération automatique de insights financiers mensuels avec recommandations personnalisées
- **Optimisation UX par IA :** Interface adaptative qui met en avant les informations les plus pertinentes selon les habitudes d'usage

### Phase 3 : Sophistication Technique

Une fois l'IA intégrée, focus sur l'excellence technique et les fonctionnalités avancées :

- **Projections Financières Personnalisées :** Modèles prédictifs simples basés sur l'historique personnel (3-6 mois, pas de complexité excessive)
- **Notifications Intelligentes :** Système d'alertes contextuelles (budget dépassé, dette oubliée, objectif d'épargne atteint)
- **Optimisations Performance :** Cache intelligent, préchargement des données, temps de réponse sub-100ms
- **Monitoring et Observabilité :** Métriques applicatives détaillées, alertes proactives, dashboards techniques

### Évolution Long-terme

Améliorations envisagées si le projet personnel évolue :

- **Extensions d'Analyse :** Intégration d'APIs externes pour comparaisons sectorielles, taux d'intérêt, inflation
- **Automatisation Avancée :** Règles personnalisées pour transactions récurrentes, budgets auto-ajustables
- **Expérience Mobile Native :** Retour éventuel vers Tauri v2 si les limitations PWA deviennent bloquantes dans l'usage quotidien (stack Svelte 5 + Tauri v2 directement compatible)