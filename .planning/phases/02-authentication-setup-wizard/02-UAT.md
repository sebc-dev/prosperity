---
status: testing
phase: 02-authentication-setup-wizard
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md, 02-06-SUMMARY.md, 02-07-SUMMARY.md
started: 2026-04-03T00:00:00Z
updated: 2026-04-03T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Cold Start Smoke Test
expected: |
  Kill any running server/service. Clear ephemeral state (temp DBs, caches, lock files). Start the application from scratch. Server boots without errors, any seed/migration completes, and a primary query (health check, homepage load, or basic API call) returns live data.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server/service. Clear ephemeral state. Start fresh with `docker compose up -d` (or `./mvnw spring-boot:run` + DB running). Server boots without errors, Flyway migrations V001–V008 run successfully (including SPRING_SESSION tables), and GET /api/auth/status returns `{"setupComplete": false}` on a fresh DB.
result: [pending]

### 2. Setup Wizard — Premier Lancement
expected: Naviguer vers http://localhost:4200 (ou via Caddy). L'application redirige automatiquement vers /setup (aucun admin n'existe). La page affiche un formulaire avec 3 champs : Email, Mot de passe, Nom affiché.
result: [pending]

### 3. Validation du Mot de Passe en Temps Réel
expected: Sur la page /setup, commencer à saisir un mot de passe. 4 règles de validation s'affichent en temps réel : ✓ 12 caractères minimum, ✓ au moins une majuscule, ✓ au moins un chiffre, ✓ au moins un caractère spécial. Les règles passent au vert au fur et à mesure qu'elles sont satisfaites.
result: [pending]

### 4. Création du Compte Admin
expected: Remplir le formulaire setup avec un email valide, un mot de passe fort (ex: Passw0rd!secur), et un nom affiché. Soumettre. Un message de succès s'affiche et l'application redirige vers /login après quelques secondes.
result: [pending]

### 5. Protection contre la Double Création (409)
expected: Tenter d'accéder à /setup après avoir déjà créé un admin. L'application redirige automatiquement vers /login (le guard noAdminGuard/setupGuard bloque l'accès). Ou : appeler POST /api/auth/setup une seconde fois → réponse 409 avec message d'erreur visible dans l'UI si la page est accessible.
result: [pending]

### 6. Connexion Réussie
expected: Sur /login, saisir l'email et le mot de passe créés à l'étape 4. Cliquer Connexion. L'application redirige vers /dashboard et affiche la page du tableau de bord.
result: [pending]

### 7. Erreur de Connexion — Identifiants Invalides
expected: Sur /login, saisir un mauvais mot de passe. L'application affiche le message générique "Identifiants invalides" (pas d'info sur l'email ou le mot de passe spécifiquement). Aucune redirection.
result: [pending]

### 8. Dashboard — Message de Bienvenue Personnalisé
expected: Après connexion réussie, le dashboard affiche "Bienvenue [nom affiché]" avec le nom exact entré lors du setup (ex: "Bienvenue Jean"). La session est active, la page de layout inclut un header avec un bouton Déconnexion.
result: [pending]

### 9. Protection des Routes — Accès Sans Session
expected: Ouvrir un onglet de navigation privée et accéder directement à http://localhost:4200/dashboard. L'application redirige vers /login sans afficher le dashboard. La session n'est pas créée.
result: [pending]

### 10. Déconnexion
expected: Depuis le dashboard, cliquer le bouton Déconnexion dans le header. La session est détruite, l'application redirige vers /login. En essayant de revenir sur /dashboard, l'application redirige à nouveau vers /login.
result: [pending]

## Summary

total: 10
passed: 0
issues: 0
pending: 10
skipped: 0
blocked: 0

## Gaps

[none yet]
