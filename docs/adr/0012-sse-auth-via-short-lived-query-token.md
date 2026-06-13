# SSE : auth via JWT short-lived en query param, heartbeat 30s, resume via last-event-id

L'API navigateur `EventSource` ne supporte pas d'envoyer des headers HTTP custom, ce qui empêche d'utiliser le header `Authorization: Bearer ...` habituel pour authentifier un flux SSE. Trois options ont été considérées : (a) cookie auth (fonctionne mais ajoute des contraintes CORS et CSRF), (b) WebSocket (sur-engineered pour notre besoin unidirectionnel), (c) **JWT short-lived en query param** (retenu). Le client appelle `POST /sse/token` (authentifié par JWT normal) pour obtenir un token scopé `sse_subscribe` valide 5 minutes, qu'il passe à `GET /sse/stream?token=...`. Le token court bénéficie d'une révocation rapide en cas de leak (les logs reverse proxy peuvent contenir les query params, mais la fenêtre d'exploitation reste limitée à 5 minutes).

**Heartbeat 30s** : ping serveur toutes les 30 secondes, sous les 100s idle timeout par défaut de Cloudflare et compatible avec tous les reverse proxies HTTP/1.1+HTTP/2 standards.

**Resume after disconnect** : header standard `Last-Event-ID` (envoyé automatiquement par `EventSource` à la reconnexion) ; le serveur maintient un **buffer ring 5 minutes / 100 events par utilisateur** et re-diffuse les events post-id. Au-delà, le client doit re-sync via REST (situation de désynchro durable, rare).

## Consequences

- Les logs reverse proxy (Caddy, Cloudflare) doivent être conscients que le query param peut contenir un token. Configuration : redacter `?token=...` dans les logs structurés Caddy. Documenté dans le runbook ops.
- Tests d'intégration spécifiques : reconnexion avec `Last-Event-ID` après simulation de drop, dépassement du buffer 5min, expiration du token 5min en cours de flux (refresh côté client requis).
- Multi-onglets : un même utilisateur a N connexions SSE actives (une par onglet), broadcast à chacune. Charge mémoire serveur acceptable pour un foyer (~ N×100 events buffered en pic).
- Cohérent avec ADR 0003 (pending_actions server-only, lecture via API + SSE).

## Addendum (S17.1) — le scope `sse_subscribe` se concrétise par l'audience `aud`

L'implémentation backend (E17 / S17.1) réalise le « token scopé `sse_subscribe` » par un **JWT HS256 dont le claim `aud` vaut `prosperity-sse`** (réglage `jwt_sse_audience`), distinct de l'audience des access tokens (`prosperity-api`, ADR 0016). Le cloisonnement passe donc par le claim **`aud`** — vérifié par PyJWT au `decode` (`audience=`), qui rejette un token d'audience différente *ou sans `aud`*. Il n'y a **pas** de claim `scope` séparé : un claim custom ne serait pas vérifié par la lib et donnerait un faux sentiment de cloisonnement. Le token reste stateless (HS256, même secret) : « révocation rapide » = **expiration 5 min** (`jwt_sse_ttl_seconds`), pas une révocation active.
