# Phase 1: Foundation - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Infrastructure Docker fonctionnelle (PostgreSQL + Spring Boot + SvelteKit), authentification email/password avec JWT, gestion des comptes bancaires (Personnel/Partagé) avec permissions, et profil utilisateur avec préférences. Pas de transactions, budgets, ni import bancaire — ces fonctionnalités arrivent dans les phases suivantes.

</domain>

<decisions>
## Implementation Decisions

### Setup initial
- Wizard au premier lancement : page /setup demande email, nom, mot de passe pour créer le compte Admin
- /setup verrouillée automatiquement dès qu'un admin existe (redirect vers /login)
- Après le wizard, redirect vers Settings pour configurer l'app
- L'admin crée le compte Standard depuis Settings > Utilisateurs (email + nom + mot de passe temporaire, changé au premier login)

### Login & session
- Page login centrée minimaliste : logo + champs email/password + bouton, fond neutre, style Linear/Vercel
- Pas de checkbox "Se souvenir de moi" — toujours connecté, refresh token 30 jours
- Expiration de session : redirect silencieux vers /login avec toast discret "Session expirée"
- Interface bilingue FR/EN avec système i18n dès le départ (sélecteur de langue dans les préférences)

### Comptes bancaires
- Formulaire complet : nom, banque, type (Personnel/Partagé), devise, solde initial, couleur
- Affichage en cards colorées groupées "Mes comptes" / "Comptes partagés"
- Double solde (réel + projeté) affiché dès la Phase 1, même si projeté = réel tant qu'il n'y a pas de transactions
- Les deux utilisateurs (Admin et Standard) peuvent créer des comptes (personnels et partagés)

### Profil & préférences
- Settings avec sidebar gauche : Profil, Préférences, Sécurité, Utilisateurs (admin seulement)
- Préférences Phase 1 : thème (clair/sombre/système), devise par défaut, langue (FR/EN), catégories favorites
- Catégories de transactions prédéfinies par défaut (Alimentation, Transport, Loisirs, Santé, Logement...) + possibilité d'ajouter des catégories custom
- Section Sécurité : changement de mot de passe uniquement (ancien + nouveau + confirmation)

### Claude's Discretion
- Design system (spacing, typography, composants UI)
- Choix de la librairie i18n SvelteKit
- Set exact de catégories prédéfinies
- Structure des migrations Liquibase
- Skeletons de chargement et états d'erreur
- Layout responsive mobile des Settings (sidebar → menu déroulant ?)

</decisions>

<specifics>
## Specific Ideas

- Style login et UI générale inspiré de Linear/Vercel — sobre, moderne, pas surchargé
- Cards de comptes avec couleur, nom de banque, et solde — visuellement riche dès le départ
- Le wizard de setup doit être une expérience soignée (première impression de l'app)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- Aucun code existant — projet greenfield
- Architecture Vertical Slice documentée dans `docs/architecture.md` avec structure de packages détaillée

### Established Patterns
- Vertical Slice : chaque feature (auth/, user/, account/) contient controller, service, repository, DTOs
- Shared kernel : domain/ (Money, UserId, AccountId), security/ (JWT, permissions), persistence/ (BaseEntity, audit)
- SvelteKit BFF pattern : browser → SvelteKit server → Spring Boot API, JWT dans httpOnly cookies
- UUIDs v7 générés côté client pour future compatibilité offline
- Money value object (BigDecimal, HALF_EVEN) dans le shared kernel

### Integration Points
- Docker Compose : PostgreSQL 16 + Spring Boot 3.3+ + SvelteKit 2
- Caddy existant sur le serveur pour HTTPS
- Liquibase pour les migrations de schéma
- Spring Security + JWT pour l'authentification

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-09*
