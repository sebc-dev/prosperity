# Runbook — canal SSE (Server-Sent Events)

> Module `backend/modules/sse` (E17 / S17.1, ADR 0012/0016). Push serveur→client :
> `POST /sse/token` → `GET /sse/stream?token=…` (`text/event-stream`).

## ⚠️ Mono-process (contrainte de déploiement critique)

Le broadcaster et le ring buffer sont **in-memory, par process**. Un event `publish`
sur le worker A **n'atteint pas** une connexion SSE ouverte sur le worker B. En
**multi-worker** (uvicorn `--workers N`) ou multi-replica, le canal SSE se **casse
silencieusement** (un client peut ne jamais recevoir un event destiné à lui).

**Déploiement V1 : un seul worker** pour le process qui sert `/sse/stream`. Un
backplane (Redis pub/sub) pour le multi-worker est un travail futur (E16 / post-MVP).

## Redaction du token dans les logs

Le token SSE transite en **query param** (`?token=…`) — l'`EventSource` ne peut pas
envoyer de header `Authorization`. Le query param est **loggable** par les reverse
proxies et les access logs.

- **Reverse proxy (Caddy / Cloudflare)** : redacter `?token=…` dans les logs
  structurés (ex. Caddy `log` + un filtre `query` masquant `token`).
- **Application** : le module `sse` ne logge **jamais** `request.url` brut ni le
  token (verrou statique `test_sse_no_url_logging`). Tout futur logging dans `sse`
  doit éviter d'émettre l'URL/le token.

## Révocation = expiration uniquement

Le token SSE est un **JWT stateless** (HS256, audience `prosperity-sse`, TTL 5 min,
`jwt_sse_ttl_seconds`). Il n'est **pas révocable activement** : « révocation rapide »
en cas de leak = **expiration au bout de 5 min**. La fenêtre d'exploitation d'un
token fuité est donc bornée à 5 min (+ le plafond de connexions par user borne le
fan-out). Ne pas promettre une révocation active aux ops.

## Heartbeat & idle timeouts

Heartbeat serveur toutes les **30 s** (`sse_heartbeat_seconds`), sous l'idle timeout
**100 s** de Cloudflare. Le flux se **ferme à l'expiration du token** (≤ 5 min) :
le client refait `POST /sse/token` puis rouvre `GET /sse/stream` (refresh côté
client requis, ADR 0012).

## Bornes (anti-DoS)

- **Connexions par user** : plafond fail-closed (`max_conns`, défaut 8) → 429 au-delà.
- **Buffer** : 100 events / 5 min par user (éviction paresseuse).
- **Rate-limit** sur `POST /sse/token` : reporté à la stack S02.5 (#73) ; en
  attendant, le plafond de connexions + le TTL 5 min sont les mitigations actives.
