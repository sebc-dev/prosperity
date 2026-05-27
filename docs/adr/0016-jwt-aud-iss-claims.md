# JWT access tokens : claims `aud` / `iss` pinnés à `prosperity-api` / `prosperity-auth`

`JWT_SECRET` est utilisé deux fois dans le module `auth` : (i) clé HS256 des access tokens (`service/jwt.py`), (ii) pepper HMAC du `token_hash` des refresh tokens (`service/refresh_tokens.py`, cf. `config.py:48-50`). N'importe quel futur artefact HS256 signé avec le même secret — un job interne qui émettrait des tokens de service, un autre composant qui ré-utiliserait `JWT_SECRET` par paresse — serait accepté par `verify_access_token` aujourd'hui, parce que `jwt.decode(...)` n'est invoqué ni avec `audience=` ni avec `issuer=` : rien dans la signature ne distingue un access token Prosperity d'un autre artefact HS256 sous la même clé. Avant d'empiler du métier sur ce verrou (E03 est le premier module protégé), nous décidons que les access tokens portent **`aud="prosperity-api"`** et **`iss="prosperity-auth"`**, et que `verify_access_token` rejette tout token qui n'a pas exactement ces deux valeurs.

## Considered Options

- **(A) Garder le statu quo (rien dans la signature ne porte le couplage service)** : tient tant que `JWT_SECRET` ne sort jamais du seul usage "access token + pepper refresh". Suppose une discipline qui n'est pas mécaniquement vérifiable, et matérialise zéro garde-fou contre la réutilisation accidentelle du secret par un futur composant. Rejeté.
- **(B) Séparer `JWT_SECRET` en deux secrets distincts (signing key vs. HMAC pepper)** : règle la cause-racine mais coûte une seconde variable d'env + un guard prod + une migration de tous les `token_hash` persistés (re-pepper). Sur-dimensionné pour le ROI tant que l'usage reste isolé à `auth`. Ré-évaluable si un autre module veut son propre HS256.
- **(C) `aud` + `iss` pinnés sur les access tokens (retenu)** : ajoute un seul checkpoint dans `verify_access_token` (`audience="prosperity-api"`, `issuer="prosperity-auth"`) et deux claims côté `issue_access_token`. Mécaniquement, un artefact HS256 signé avec le même secret mais sans ces claims (ou avec d'autres valeurs) est rejeté. Coût : deux champs Pydantic `Settings`, deux claims dans le payload (~30 octets), aucune migration data. Couvre 100 % du scénario "secret partagé entre usages distincts" tant que les usages futurs ne se mettent pas à mentir sur leur `aud` (cas auquel **B** redevient la bonne réponse).

## Naming

| Claim | Valeur | Pourquoi |
|---|---|---|
| `aud` | `prosperity-api` | API REST destinatrice. Si un compagnon (worker, CLI admin) émerge un jour avec son propre auth flow, il devra émettre des tokens à un `aud` distinct et ne sera pas accepté par les routes API par accident. |
| `iss` | `prosperity-auth` | Émetteur. Le module `auth` est aujourd'hui l'unique source de tokens HS256 ; pinner le `iss` rend explicite que la confiance est ancrée sur ce module et pas sur "tout ce qui signe avec `JWT_SECRET`". |

Valeurs littérales hardcodées dans `Settings` comme defaults (`jwt_audience`, `jwt_issuer`), surchargeables par env (`JWT_AUDIENCE`, `JWT_ISSUER`) pour permettre staging/prod de diverger si jamais nécessaire — mais en pratique, le couple reste stable.

## Stratégie de rotation

- **Rotation `JWT_SECRET`** : invalide déjà tous les access tokens en vol (signature ne valide plus) et tous les refresh tokens persistés (pepper HMAC change → `token_hash` ne match plus). `aud`/`iss` ne changent pas la sémantique : la rotation reste un événement "forced re-login" déjà documenté dans `config.py:48-50`.
- **Renommage `aud` ou `iss`** : opération breaking. Tout access token émis sous l'ancienne valeur sera rejeté à la prochaine vérification. Le TTL des access tokens est 15 min ; un renommage déployé d'un coup laisse au pire 15 min de 401 sur l'instance avant que les clients refresh un nouveau pair. Dans la pratique, on n'attend pas avoir besoin de renommer (les valeurs sont stables par construction). Si un jour c'est nécessaire (ex. ouverture multi-tenant), prévoir une grace period où `verify_access_token` accepte un **set** d'`aud` valides pendant 15 min, puis bascule sur la nouvelle seule.
- **Pas de grace period au déploiement initial** : la décision atterrit avant E03, donc avant que la moindre instance soit en prod. Le 15 min de TTL est de toute façon la grace period naturelle pour les access tokens ; les refresh tokens ne portent pas `aud`/`iss` (ce sont des opaques en DB, pas des JWT) — ils ne sont pas affectés.

## Consequences

- `Settings.jwt_audience` et `Settings.jwt_issuer` (defaults `"prosperity-api"` / `"prosperity-auth"`) ajoutés à `backend/config.py`. Pas de guard prod spécifique : ces valeurs sont des constantes de service, pas des secrets.
- `issue_access_token` ajoute les claims `aud` et `iss` au payload.
- `verify_access_token` passe `audience=settings.jwt_audience` et `issuer=settings.jwt_issuer` à `jwt.decode`. Un token sans `aud` (jose lève `JWTClaimsError`), avec un `aud` différent, ou avec un `iss` différent, est rejeté en `InvalidTokenError` — pas en `ExpiredTokenError` (l'incohérence n'est pas une expiration, et la réponse 401 unifiée du dependency `get_current_user` rend la distinction invisible côté client de toute façon).
- Tests unitaires (`tests/unit/test_auth_jwt.py`) épinglent : round-trip avec les defaults, rejet d'un token sans `aud`, mauvais `aud`, sans `iss`, mauvais `iss`. Ces tests verrouillent le défense-en-profondeur contre une régression future qui retirerait `audience=` ou `issuer=` de `jwt.decode`.
- Le futur module `mcp` qui émettrait ses propres tokens (cf. ADR 0004) doit utiliser un **`aud` distinct** (ex. `prosperity-mcp`) — l'API REST ne doit pas accepter de tokens MCP. Idem si un jour les SSE tokens passent par JWT plutôt que par token DB short-lived (cf. ADR 0012).
- Pas de migration data. Pas de nouvelle variable d'env requise — les defaults suffisent. Reste l'override possible via `JWT_AUDIENCE` / `JWT_ISSUER` pour usages exotiques (staging multi-tenant, etc.).
