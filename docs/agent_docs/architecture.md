# Architecture -- Prosperity

## Pattern
Architecture layered classique (Controller / Service / Repository) organisee par feature, avec abstraction strategique uniquement la ou c'est justifie (connecteur bancaire). API REST monolithique + SPA separee.

### Pourquoi pas hexagonal ?
L'hexagonal (ports/adapters generalises) ajoute du boilerplate sans benefice reel ici : chaque port n'a qu'un seul adapter (un seul type de base de donnees, un seul framework web). La seule abstraction justifiee est le connecteur bancaire (Plaid interchangeable avec Powens/Salt Edge). Le reste utilise directement Spring Data et Spring MVC.

### Principes
- **Package-by-feature** : chaque feature (account, transaction, envelope...) est un package autonome avec controller, service, repository, entite
- **Abstraction strategique** : interface uniquement quand plusieurs implementations sont prevues (connecteur bancaire)
- **Value Objects** : Money (BigDecimal), TransactionState et autres types metier expriment les regles du domaine
- **Spring Data comme repository** : pas de port intermediaire devant Spring Data JPA -- c'est deja une interface

## Composants
| Composant | Responsabilite | Technologie |
|-----------|----------------|-------------|
| Caddy | Reverse proxy, HTTPS auto, sert les fichiers statiques Angular, proxy /api/* | Caddy 2.11.x |
| API REST | Logique metier, endpoints REST, auth BFF | Spring Boot 4.0.x + Spring Security 7.0.x |
| SPA / PWA | Dashboard web + app mobile (meme build, service worker active) | Angular 21, PrimeNG 21.x, ngx-echarts, Tailwind v4 |
| Base de donnees | Stockage persistant, migrations | PostgreSQL 17 + Flyway 11.x |
| Connecteur bancaire | Synchronisation bancaire (derriere interface abstraite) | Plaid API (EU/FR) |

## Schema

```
                         +──────────────+
                         |    Caddy      |
                         |  :80 / :443   |
                         +──────┬───────+
                                |
                 +──────────────┼──────────────+
                 |              |              |
           /api/*         /            /pwa
                 |              |              |
        +────────v──+   +──────v──────+  (meme build
        |  Spring    |   |   Angular    |   Angular,
        |  Boot API  |   |   SPA/PWA   |   SW active)
        |  :8080     |   |   (static)  |
        +─────┬──────+   +─────────────+
              |
    +─────────┼─────────────+
    |         |             |
+───v───+ +──v────────+ +──v──────────+
| App   | |            | |             |
|Logic  | | PostgreSQL | | Plaid API   |
|       | |  :5432     | | (external)  |
+───────+ +────────────+ +─────────────+
```

## Structure backend (package-by-feature)

```
src/main/java/com/prosperity/
  account/
    AccountController.java      # REST endpoints
    AccountService.java         # Logique metier
    AccountRepository.java      # Spring Data JPA interface
    Account.java                # Entite JPA
    AccountDto.java             # DTO REST
  transaction/
    TransactionController.java
    TransactionService.java
    TransactionRepository.java
    Transaction.java
    TransactionDto.java
  envelope/
    ...
  category/
    ...
  banking/                      # Abstraction strategique
    BankConnector.java          # Interface (seul point d'abstraction justifie)
    BankTransaction.java        # Modele commun import
    plaid/
      PlaidBankConnector.java   # Implementation Plaid
      PlaidConfig.java
  auth/
    AuthController.java
    AuthService.java
    ...
  admin/
    ...
  shared/
    Money.java                  # Value Object (BigDecimal, precision 2)
    TransactionState.java       # Enum : MANUAL_UNMATCHED, IMPORTED_UNMATCHED, MATCHED
    config/                     # Spring config globale, security, CORS, etc.
```

## Flux de donnees

1. L'utilisateur accede via Caddy (HTTPS auto, :443)
2. Caddy sert les fichiers statiques Angular (SPA + PWA)
3. Les appels /api/* sont proxied vers Spring Boot :8080
4. Les controllers REST appellent les services
5. Les services implementent la logique metier et appellent les repositories
6. Les repositories (Spring Data JPA) accedent a PostgreSQL
7. Le connecteur bancaire (BankConnector interface) est injecte dans les services qui en ont besoin

## Authentification

BFF cookie flow :
- Spring Boot gere les JWT cote serveur
- Le frontend recoit des cookies httpOnly, Secure, SameSite=Strict
- Protection CSRF via CookieCsrfTokenRepository (compatible Angular HttpClientXsrfModule)
- Refresh tokens stockes cote serveur uniquement

## Points d'entree
- **Web** : dashboard Angular via navigateur (Caddy :443)
- **Mobile** : PWA Angular (meme URL, service worker active)
- **API** : REST endpoints Spring Boot (via Caddy /api/*)

## Deploiement
Docker Compose avec 3 services :
- `db` : PostgreSQL 17 (Alpine)
- `backend` : Spring Boot (Temurin 21 JRE)
- `caddy` : Caddy 2.11.x (sert Angular static + proxy API)
