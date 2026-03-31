# Phase 02 — Angular Authentication Layer: Rapport detaille

**Branche:** `gsd/phase-02-authentication-setup-wizard`
**Date:** 2026-03-31
**Scope:** 9 fichiers modifies/ajoutes, +537 lignes

## Table des matieres

1. [Vue d'ensemble des changements](#1-vue-densemble-des-changements)
2. [Explication detaillee — Fichiers de production](#2-explication-detaillee--fichiers-de-production)
   - [2.1 auth.service.ts](#21-authservicets)
   - [2.2 auth.guard.ts](#22-authguardts)
   - [2.3 auth.interceptor.ts](#23-authinterceptorts)
   - [2.4 app.config.ts](#24-appconfigts)
   - [2.5 angular.json](#25-angularjson)
   - [2.6 proxy.conf.json](#26-proxyconfjson)
3. [Explication detaillee — Fichiers de tests](#3-explication-detaillee--fichiers-de-tests)
   - [3.1 auth.service.spec.ts](#31-authservicespects)
   - [3.2 auth.guard.spec.ts](#32-authguardspects)
   - [3.3 auth.interceptor.spec.ts](#33-authinterceptorspects)
4. [Validation Angular 21 Best Practices](#4-validation-angular-21-best-practices)
5. [Validation Testing Principles](#5-validation-testing-principles)
6. [Resume](#6-resume)

---

## 1. Vue d'ensemble des changements

### Commits (du plus ancien au plus recent)

| Commit | Description |
|--------|-------------|
| `c75b207` | Cree AuthService avec gestion d'etat par signals |
| `17514e1` | Ajoute guards, interceptor HTTP, config XSRF et proxy dev |
| `77fc645` | Ajoute les tests unitaires pour AuthService et guards |
| `6808416` | Applique les corrections de code review |
| `7e12f96` | Formatage Prettier |

### Fichiers modifies

| Fichier | Type | Lignes |
|---------|------|--------|
| `src/app/auth/auth.service.ts` | Nouveau | +91 |
| `src/app/auth/auth.guard.ts` | Nouveau | +41 |
| `src/app/auth/auth.interceptor.ts` | Nouveau | +23 |
| `src/app/app.config.ts` | Modifie | +11/-1 |
| `angular.json` | Modifie | +3 |
| `proxy.conf.json` | Nouveau | +6 |
| `src/app/auth/auth.service.spec.ts` | Nouveau | +132 |
| `src/app/auth/auth.guard.spec.ts` | Nouveau | +126 |
| `src/app/auth/auth.interceptor.spec.ts` | Nouveau | +105 |

---

## 2. Explication detaillee — Fichiers de production

### 2.1 `auth.service.ts`

**Role:** Service singleton qui centralise toute la logique d'authentification et l'etat de l'utilisateur connecte.

#### Interfaces

**`UserResponse`** (lignes 5-9)
Represente la reponse du backend quand un utilisateur est authentifie. Contient `displayName`, `email` et `role`. Utilisee comme type de retour pour les appels `login`, `setup` et `checkSession`.

**`SetupRequest`** (lignes 11-15)
Corps de la requete pour creer le premier utilisateur admin lors du wizard de setup initial. Contient `email`, `password` et `displayName`.

**`LoginRequest`** (lignes 17-20)
Corps de la requete de connexion : `email` et `password`.

**`StatusResponse`** (lignes 22-24)
Reponse du endpoint `GET /api/auth/status`. Le champ `setupComplete` indique si l'application a deja un administrateur configure.

**`AuthError`** (lignes 26-30)
Type d'erreur custom qui encapsule le code HTTP (`status`), un message lisible (`message`), et la reponse brute Angular (`original: HttpErrorResponse`) pour le debug.

#### Proprietes

**`currentUser`** (ligne 34)
```typescript
private currentUser = signal<UserResponse | null>(null);
```
Signal Angular qui stocke l'utilisateur actuellement connecte. `null` signifie "non authentifie". C'est la **source de verite unique** pour l'etat d'authentification du frontend. Le choix d'un `signal()` plutot qu'un `BehaviorSubject` RxJS est l'approche recommandee Angular 21.

**`http`** (ligne 36)
```typescript
private readonly http = inject(HttpClient);
```
Injection du client HTTP Angular via la fonction `inject()` — pattern fonctionnel moderne, sans injection par constructeur.

**`isAuthenticated`** (ligne 38)
```typescript
readonly isAuthenticated = computed(() => this.currentUser() !== null);
```
Signal derive (computed). Retourne `true` si `currentUser` n'est pas `null`. Se recalcule automatiquement quand `currentUser` change. Les composants peuvent lire `authService.isAuthenticated()` dans un template et l'affichage se met a jour reactivemet.

**`user`** (ligne 39)
```typescript
readonly user = computed(() => this.currentUser());
```
Expose `currentUser` en lecture seule via un computed. Les composants accedent a l'utilisateur via `authService.user()` sans pouvoir modifier le signal directement (le signal source est `private`).

#### Methodes

**`mapError(err)`** (lignes 41-48)
```typescript
private mapError(err: HttpErrorResponse): Observable<never>
```
Methode privee de transformation d'erreur. Prend une `HttpErrorResponse` Angular brute et la convertit en `AuthError` type. La logique d'extraction du message :
1. Si `err.error` est un string → l'utiliser directement (backend renvoie du texte brut)
2. Sinon, chercher `err.error.error` (format JSON Spring Boot standard : `{"error": "Bad credentials"}`)
3. En dernier recours, `err.statusText` (ex: "Unauthorized", "Not Found")

Retourne `throwError(() => authError)` — l'erreur est re-propagee dans le stream RxJS pour que les composants puissent la gerer.

**`checkSession()`** (lignes 50-58)
```typescript
checkSession(): Observable<UserResponse | null>
```
Appelle `GET /api/auth/me` pour verifier si l'utilisateur a une session active cote serveur.
- **Succes** (cookie de session valide) : le `tap` met a jour le signal `currentUser` avec l'utilisateur recu
- **Erreur** (401, pas de session) : le `catchError` reset `currentUser` a `null` et retourne `of(null)` — l'erreur est **avalee** (pas propagee)

Cette methode est appelee par les guards a chaque navigation pour verifier l'etat reel de la session. L'erreur est avalee car un 401 sur `/me` est un cas nominal (pas connecte), pas une vraie erreur.

**`checkStatus()`** (lignes 60-62)
```typescript
checkStatus(): Observable<StatusResponse>
```
Appelle `GET /api/auth/status`. Aucun side effect, aucune gestion d'erreur — c'est le consommateur (`setupGuard`) qui gere. Retourne simplement si le setup initial est fait ou non.

**`login(request)`** (lignes 64-69)
```typescript
login(request: LoginRequest): Observable<UserResponse>
```
`POST /api/auth/login` avec email + password.
- **Succes** : le backend cree une session cookie HTTP-only, le `tap` stocke l'utilisateur dans le signal
- **Erreur** : transformee en `AuthError` via `mapError()` et propagee au composant pour affichage (ex: "Identifiants incorrects")

**`setup(request)`** (lignes 71-75)
```typescript
setup(request: SetupRequest): Observable<UserResponse>
```
`POST /api/auth/setup` — cree le premier administrateur. Difference cle avec `login()` : **pas de `tap`** pour mettre a jour `currentUser`. Le setup ne connecte pas automatiquement l'utilisateur — il devra se connecter ensuite via le formulaire de login. L'erreur est transformee en `AuthError` (ex: 409 si un admin existe deja).

**`logout()`** (lignes 77-85)
```typescript
logout(): Observable<void>
```
`POST /api/auth/logout` — invalide la session cote serveur.
- **Succes** : le `tap` reset `currentUser` a `null`
- **Erreur** : reset `currentUser` a `null` **quand meme** (l'utilisateur est considere deconnecte localement meme si le backend echoue), mais l'erreur est re-propagee via `throwError` pour que le composant puisse afficher un warning si necessaire

Cette approche "reset dans tous les cas" est defensive : si le serveur est injoignable, l'utilisateur ne reste pas bloque dans un etat "connecte" cote frontend.

**`clearUser()`** (lignes 88-90)
```typescript
clearUser(): void
```
Reset le signal a `null`. Marque `@internal` dans le JSDoc — reserve exclusivement a `authInterceptor` quand il recoit un 401 sur un appel API. Separe les responsabilites : l'interceptor nettoie l'etat, le composant ou l'interceptor gere la navigation.

---

### 2.2 `auth.guard.ts`

**Role:** Trois guards fonctionnels (`CanActivateFn`) qui protegent les routes selon l'etat d'authentification.

**`authGuard`** (lignes 6-16)
```typescript
export const authGuard: CanActivateFn = () => { ... }
```
Protege les routes authentifiees (ex: `/dashboard`, `/accounts`).
1. Appelle `authService.checkSession()` pour verifier la session aupres du serveur
2. Si l'utilisateur est connecte (`user` non null) → retourne `true`, la navigation continue
3. Si non connecte → retourne `router.createUrlTree(['/login'])`, Angular redirige vers `/login`

Le choix de `createUrlTree` plutot que `router.navigate()` est important : il retourne une `UrlTree` qui s'integre dans le cycle de navigation Angular (le router peut annuler proprement la navigation en cours).

**`unauthenticatedGuard`** (lignes 18-28)
```typescript
export const unauthenticatedGuard: CanActivateFn = () => { ... }
```
Protege les routes publiques (login, setup). Empeche un utilisateur deja connecte d'acceder au formulaire de login.
1. Appelle `checkSession()`
2. Si **pas** connecte → `true`, acces autorise
3. Si connecte → redirige vers `/dashboard`

C'est le guard inverse de `authGuard`.

**`setupGuard`** (lignes 30-41)
```typescript
export const setupGuard: CanActivateFn = () => { ... }
```
Protege la route du wizard de setup (`/setup`).
1. Appelle `authService.checkStatus()` pour verifier si le setup initial est deja fait
2. Si `setupComplete === false` → `true`, le wizard est accessible
3. Si `setupComplete === true` → redirige vers `/login`
4. Si l'appel echoue (serveur inaccessible) → redirige aussi vers `/login` par securite (`catchError`)

Le `catchError` sur ce guard est une decision defensive : si on ne peut pas determiner l'etat du setup, mieux vaut rediriger vers login que laisser l'acces au wizard.

**Note architecturale :** Les trois guards appellent l'API a chaque navigation. Il n'y a pas de cache local. C'est un choix delibere : la source de verite est toujours le serveur, ce qui evite les desynchronisations (ex: session expiree cote serveur mais frontend croit etre connecte).

---

### 2.3 `auth.interceptor.ts`

**Role:** Intercepteur HTTP global qui reagit aux reponses 401 sur les appels API.

**`AUTH_CHECK_URLS`** (ligne 7)
```typescript
const AUTH_CHECK_URLS = ['/api/auth/me', '/api/auth/status'];
```
Liste des URLs d'authentification a exclure du traitement 401. Ces URLs retournent naturellement des 401 quand l'utilisateur n'est pas connecte — ce n'est pas une erreur a traiter.

**`isAuthCheckUrl(url)`** (ligne 8)
```typescript
const isAuthCheckUrl = (url: string): boolean => AUTH_CHECK_URLS.some((u) => url.includes(u));
```
Helper qui verifie si une URL fait partie des URLs exclues. Utilise `includes()` plutot que `===` pour gerer les query params eventuels.

**`authInterceptor`** (lignes 10-23)
```typescript
export const authInterceptor: HttpInterceptorFn = (req, next) => { ... }
```
Intercepteur fonctionnel (pas class-based). Pour chaque requete HTTP :
1. Laisse la requete passer normalement via `next(req)`
2. Intercepte les **reponses** en erreur via `catchError`
3. Si l'erreur est un **401** ET l'URL commence par `/api/` ET l'URL n'est **pas** une URL d'auth check :
   - Appelle `authService.clearUser()` pour nettoyer l'etat
   - Redirige vers `/login`
4. Dans **tous les cas**, re-propage l'erreur via `throwError` pour que le composant appelant puisse aussi reagir

**Trois conditions de filtrage (ligne 16) :**
- `error.status === 401` → ne reagit qu'aux "non autorise", pas aux 403, 500, etc.
- `req.url.startsWith('/api/')` → ignore les appels vers des URLs externes (CDN, analytics, etc.)
- `!isAuthCheckUrl(req.url)` → evite une boucle : `checkSession()` retourne 401 quand pas connecte, ce qui est normal et ne doit pas declencher de redirection

---

### 2.4 `app.config.ts`

**Role:** Configuration globale de l'application Angular.

**Changements :**
```typescript
// AVANT
providers: [provideBrowserGlobalErrorListeners(), provideRouter(routes)]

// APRES
providers: [
  provideBrowserGlobalErrorListeners(),
  provideRouter(routes),
  provideHttpClient(
    withXsrfConfiguration({ cookieName: 'XSRF-TOKEN', headerName: 'X-XSRF-TOKEN' }),
    withInterceptors([authInterceptor]),
  ),
]
```

Trois ajouts :

1. **`provideHttpClient()`** — Active le module HTTP Angular de maniere standalone (sans `HttpClientModule`). C'est l'API moderne Angular 21.

2. **`withXsrfConfiguration()`** — Configure la protection CSRF/XSRF :
   - `cookieName: 'XSRF-TOKEN'` : le cookie que Spring Security depose dans le navigateur
   - `headerName: 'X-XSRF-TOKEN'` : le header qu'Angular envoie automatiquement dans chaque requete mutante (POST, PUT, DELETE)

   Ce couple cookie/header est la convention par defaut de `CookieCsrfTokenRepository` cote Spring Security 7. Angular lit le cookie et le renvoie comme header — le serveur verifie que les deux correspondent. Cela protege contre les attaques CSRF sans token dans le body.

3. **`withInterceptors([authInterceptor])`** — Enregistre l'intercepteur 401 globalement pour toutes les requetes HTTP.

---

### 2.5 `angular.json`

**Changement :** Ajout de la configuration proxy sur la cible `serve`.

```json
"serve": {
  "builder": "@angular/build:dev-server",
  "options": {
    "proxyConfig": "proxy.conf.json"
  }
}
```

En developpement, `ng serve` (port 4200) proxifie les requetes `/api/*` vers le backend Spring Boot (port 8080). Cela evite les erreurs CORS — le navigateur voit une seule origine.

---

### 2.6 `proxy.conf.json`

**Nouveau fichier :**
```json
{
  "/api": {
    "target": "http://localhost:8080",
    "secure": false
  }
}
```

- `"/api"` : toute requete dont l'URL commence par `/api` est proxifiee
- `"target"` : redirigee vers `http://localhost:8080` (Spring Boot)
- `"secure": false` : accepte les certificats auto-signes (dev uniquement)

Ce fichier n'est utilise qu'en dev. En production, Caddy gere le routage `/api/*` → backend.

---

## 3. Explication detaillee — Fichiers de tests

### 3.1 `auth.service.spec.ts`

**Configuration** (lignes 10-20)
```typescript
beforeEach(() => {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  service = TestBed.inject(AuthService);
  httpTesting = TestBed.inject(HttpTestingController);
});
afterEach(() => { httpTesting.verify(); });
```
- `provideHttpClient()` + `provideHttpClientTesting()` : API moderne (pas l'ancien `HttpClientTestingModule`)
- `httpTesting.verify()` dans `afterEach` : verifie qu'aucune requete HTTP n'est restee sans reponse

#### Tests

**`login_sets_current_user_on_success`** (lignes 22-33)
Verifie que `login()` met a jour les signals `isAuthenticated` et `user` apres un login reussi. Valide aussi que la methode HTTP est `POST`.

**`logout_clears_current_user`** (lignes 35-50)
Se connecte d'abord via `login()`, puis verifie que `logout()` remet `isAuthenticated` a `false` et `user` a `null`.

**`check_session_sets_user_when_authenticated`** (lignes 52-61)
Verifie que `checkSession()` met a jour `isAuthenticated` a `true` quand le serveur retourne un utilisateur.

**`check_session_clears_user_on_401`** (lignes 63-70)
Verifie que `checkSession()` met `isAuthenticated` a `false` quand le serveur retourne 401 (pas de session).

**`setup_does_not_set_current_user`** (lignes 72-83)
Verifie que `setup()` ne connecte **pas** l'utilisateur automatiquement : apres un setup reussi, `isAuthenticated` reste `false`.

**`check_status_returns_setup_complete`** (lignes 85-94)
Verifie que `checkStatus()` retourne correctement la valeur `setupComplete` du serveur.

**`login_returns_typed_auth_error_on_failure`** (lignes 96-113)
Verifie que `login()` transforme un 401 en `AuthError` type avec le bon `status` (401) et `message` ("Identifiants invalides"). Verifie aussi que l'utilisateur reste non authentifie.

**`setup_returns_typed_auth_error_on_conflict`** (lignes 115-131)
Verifie que `setup()` transforme un 409 Conflict en `AuthError` avec le bon message ("Admin already exists").

---

### 3.2 `auth.guard.spec.ts`

**Configuration** (lignes 21-40)
```typescript
provideRouter([
  { path: 'login', redirectTo: '' },
  { path: 'dashboard', redirectTo: '' },
]),
provideHttpClient(),
provideHttpClientTesting(),
```
Des routes factices sont enregistrees pour que `createUrlTree` puisse generer des `UrlTree` valides.

**Helper `runGuard()`** (lignes 13-19)
```typescript
function runGuard(guard: typeof authGuard): Observable<boolean | UrlTree> {
  let obs!: Observable<boolean | UrlTree>;
  TestBed.runInInjectionContext(() => {
    obs = guard(MOCK_ROUTE, MOCK_STATE) as Observable<boolean | UrlTree>;
  });
  return obs;
}
```
Les functional guards utilisent `inject()` en interne, ce qui necessite un contexte d'injection Angular. `runInInjectionContext()` fournit ce contexte dans les tests.

#### Tests authGuard

**`allows_access_when_authenticated`** (lignes 43-55)
Simule une session valide (flush user), verifie que le guard retourne `true`.

**`redirects_to_login_when_not_authenticated`** (lignes 57-66)
Simule un 401, verifie que le guard retourne une `UrlTree` vers `/login`.

#### Tests unauthenticatedGuard

**`allows_access_when_not_authenticated`** (lignes 70-78)
Simule un 401, verifie que le guard retourne `true` (acces autorise aux pages publiques).

**`redirects_to_dashboard_when_authenticated`** (lignes 81-93)
Simule une session valide, verifie la redirection vers `/dashboard`.

#### Tests setupGuard

**`allows_access_when_setup_not_complete`** (lignes 97-103)
Simule `setupComplete: false`, verifie que le guard retourne `true`.

**`redirects_to_login_when_setup_complete`** (lignes 106-112)
Simule `setupComplete: true`, verifie la redirection vers `/login`.

**`redirects_to_login_when_status_endpoint_errors`** (lignes 115-123)
Simule une erreur 500 sur `/api/auth/status`, verifie que le guard redirige vers `/login` par securite.

---

### 3.3 `auth.interceptor.spec.ts`

**Configuration** (lignes 13-24)
```typescript
provideHttpClient(withInterceptors([authInterceptor])),
provideHttpClientTesting(),
```
L'intercepteur est enregistre avec `withInterceptors()` — API fonctionnelle moderne. Le `HttpClient` injecte dans les tests passe reellement par l'intercepteur.

**Helper `loginFirst()`** (lignes 30-34)
Simule un login reussi pour etablir un etat "authentifie" avant les tests. C'est un mecanisme reutilisable (DRY) tandis que les scenarios restent explicites (DAMP).

#### Tests

**`clears_user_on_401_for_api_routes`** (lignes 39-50)
Se connecte, fait un appel API qui retourne 401, verifie que `isAuthenticated` passe a `false`. C'est le cas nominal de l'intercepteur.

**`does_not_clear_user_on_401_for_auth_me`** (lignes 52-62)
Se connecte, fait un appel a `/api/auth/me` qui retourne 401, verifie que `isAuthenticated` reste `true`. L'intercepteur ne doit **pas** reagir aux URLs d'auth check.

**`does_not_clear_user_on_401_for_auth_status`** (lignes 64-76)
Meme verification pour `/api/auth/status`.

**`does_not_clear_user_on_non_401_errors`** (lignes 78-90)
Se connecte, fait un appel API qui retourne 500, verifie que `isAuthenticated` reste `true`. L'intercepteur ne reagit qu'aux 401.

**`does_not_clear_user_on_401_for_external_urls`** (lignes 92-104)
Se connecte, fait un appel vers `https://external.com/api` qui retourne 401, verifie que `isAuthenticated` reste `true`. L'intercepteur ne reagit qu'aux URLs commencant par `/api/`.

---

## 4. Validation Angular 21 Best Practices

Validation effectuee avec l'outil `get_best_practices` du MCP Angular CLI, configuree pour le workspace Angular 21 du projet.

### 4.1 `auth.service.ts`

| Regle Angular 21 | Statut | Detail |
|-------------------|--------|--------|
| `inject()` au lieu de constructor injection | CONFORME | `inject(HttpClient)` ligne 36 |
| Signals pour le state management | CONFORME | `signal()` ligne 34, `computed()` lignes 38-39 |
| `providedIn: 'root'` pour singleton | CONFORME | Ligne 32 |
| Pas de `mutate` sur signals | CONFORME | Utilise `.set()` partout |
| Strict typing (pas de `any`) | CONFORME | Toutes les interfaces typees, zero `any` |
| Single responsibility | CONFORME | Uniquement auth/session |
| `computed()` pour derived state | CONFORME | `isAuthenticated` et `user` |
| Type inference quand le type est evident | CONFORME | Inference utilisee sur les closures |

### 4.2 `auth.guard.ts`

| Regle Angular 21 | Statut | Detail |
|-------------------|--------|--------|
| Functional guards (`CanActivateFn`) | CONFORME | Pas de class-based guards |
| `inject()` | CONFORME | `inject(AuthService)`, `inject(Router)` |
| Pas de `any` | CONFORME | Types inferes correctement |
| Pas de standalone dans decorator | N/A | Pas de component/directive |

### 4.3 `auth.interceptor.ts`

| Regle Angular 21 | Statut | Detail |
|-------------------|--------|--------|
| Functional interceptor (`HttpInterceptorFn`) | CONFORME | Pas de class-based `HttpInterceptor` |
| `inject()` | CONFORME | `inject(Router)`, `inject(AuthService)` |
| Pas de `any` | CONFORME | `HttpErrorResponse` type |
| Single responsibility | CONFORME | Uniquement gestion 401 |

### 4.4 `app.config.ts`

| Regle Angular 21 | Statut | Detail |
|-------------------|--------|--------|
| `provideHttpClient()` standalone | CONFORME | Pas d'ancien `HttpClientModule` |
| `withInterceptors()` fonctionnel | CONFORME | API moderne |
| `withXsrfConfiguration()` | CONFORME | Configuration explicite du couple cookie/header |

### 4.5 Tests (les 3 fichiers spec)

| Regle Angular 21 | Statut | Detail |
|-------------------|--------|--------|
| `provideHttpClient()` + `provideHttpClientTesting()` | CONFORME | API moderne, pas `HttpClientTestingModule` |
| `provideRouter()` | CONFORME | API moderne, pas `RouterTestingModule` |
| `TestBed.runInInjectionContext()` | CONFORME | Requis pour functional guards |
| `withInterceptors()` dans les tests | CONFORME | Intercepteur teste via l'API reelle |

---

## 5. Validation Testing Principles

Validation contre les regles definies dans `.claude/rules/testing-principles.md`.

### 5.1 Structure et nommage

| Principe | Statut | Detail |
|----------|--------|--------|
| Structure AAA (Arrange-Act-Assert) | CONFORME | Sections separees par ligne blanche, commentaires AAA |
| Nommage `scenario_description_and_expected_result` | CONFORME | Ex: `login_sets_current_user_on_success`, `clears_user_on_401_for_api_routes` |
| Un test = un concept logique | CONFORME | Chaque test verifie un seul comportement |

### 5.2 Couverture des cas (EP + BVA)

| Type de cas | auth.service | auth.guard | auth.interceptor |
|-------------|-------------|------------|-------------------|
| Happy path | login, checkSession, setup, checkStatus | Acces autorise x3 | N/A (intercepteur reactif) |
| Erreurs | 401 checkSession, 401 login, 409 setup | 401 → redirect x2 | 401 API → clear user |
| Edge cases | setup ne connecte pas | Erreur serveur 500 | 401 sur URL exclue, 401 externe, erreur non-401 |

### 5.3 Test Doubles

| Principe | Statut | Detail |
|----------|--------|--------|
| Minimal usage de doubles | CONFORME | `HttpTestingController` est le seul double (fake HTTP) |
| Pas de mock excessif | CONFORME | Zero mock, uniquement le fake HTTP fourni par Angular |
| <= 2-3 doubles par test | CONFORME | 1 seul double (httpTesting) |
| Assertions sur comportement observable | CONFORME | Signals publics (`isAuthenticated`, `user`), pas d'etat interne |

### 5.4 Proprietes FIRST

| Propriete | Statut | Detail |
|-----------|--------|--------|
| **F**ast | CONFORME | Zero appel reseau reel, tout via `HttpTestingController` |
| **I**solated | CONFORME | `beforeEach` reinitialise TestBed, `afterEach` verifie les requetes |
| **R**epeatable | CONFORME | Deterministe, pas de date/random/reseau |
| **S**elf-validating | CONFORME | Assertions explicites, pas de verification manuelle |
| **T**imely | CONFORME | Tests ecrits avec le code (meme branche) |

### 5.5 Anti-patterns

| Anti-pattern | Statut | Detail |
|--------------|--------|--------|
| The Liar (assertions absentes) | ABSENT | Chaque test a des assertions concretes |
| The Mockery (plus de mocks que d'assertions) | ABSENT | 1 double vs 1-3 assertions par test |
| The Inspector (acces prive) | ABSENT | Uniquement API publique (signals, observables) |
| The Giant (> 50 lignes) | ABSENT | Tests entre 5 et 15 lignes |
| Fragile Test (casse au refactoring) | ABSENT | Assertions sur outputs, pas sur implementation |
| Free Ride (assertion non liee) | ABSENT | Chaque test verifie un seul concept |
| Flaky (sleep, Date.now) | ABSENT | Zero temporalite, zero reseau reel |

### 5.6 DAMP > DRY

| Aspect | Statut | Detail |
|--------|--------|--------|
| Scenarios explicites | CONFORME | Chaque test decrit son scenario en entier |
| Mecanismes reutilisables | CONFORME | `runGuard()`, `loginFirst()` extraits en helpers |
| `beforeEach` ne masque pas l'intent | CONFORME | Setup technique uniquement (TestBed), pas de donnees metier |

---

## 6. Resume

### Bilan quantitatif

| Metrique | Valeur |
|----------|--------|
| Fichiers de production ajoutes | 4 (service, guard, interceptor, proxy) |
| Fichiers de production modifies | 2 (app.config, angular.json) |
| Fichiers de tests ajoutes | 3 |
| Lignes ajoutees | 537 |
| Tests unitaires | 17 |
| Non-conformites Angular 21 | 0 |
| Non-conformites Testing Principles | 0 |
| Anti-patterns detectes | 0 |

### Verdict

**Tous les fichiers Angular sont conformes** aux bonnes pratiques Angular 21 et aux principes de test du projet. Le code utilise systematiquement les patterns modernes (signals, functional guards/interceptors, `inject()`, `provideHttpClient`) et les tests couvrent les cas nominaux, les erreurs et les cas limites sans recourir a des mocks excessifs.
