# MCP comme module à part entière, consommateur unidirectionnel

F14 (MCP server) porte un vrai domaine (pending actions, audit lineage immutable, heuristiques de compromission, rate limiting par PAT, double format JSON+markdown des tools d'analyse, deux transports stdio+HTTP) qui n'a sa place ni dans une couche d'exposition pure comme `api/`, ni éclaté entre plusieurs modules. Nous décidons de créer `modules/mcp/` comme **module à part entière** avec son propre `domain.py`, `service.py`, `tools/`, `transports/`, et d'imposer un **sens d'import strictement unidirectionnel : `mcp → autres modules`**. Aucun module métier ne sait que MCP existe ; les tools `propose_*` créent des PendingAction et ne mutent jamais directement une entité métier — la confirmation utilisateur déclenche l'écriture via les services métier normaux.

Le `PATToken` lui-même reste dans `modules/auth/` (cohérent avec JWT/refresh), seul l'usage agentique (heuristiques, rate-limit, audit) appartient à `mcp/`.

## Consequences

- La règle `Independence` de la stratégie de test (import-linter) telle qu'écrite est intenable avec ce module : `mcp` doit explicitement être exclu, ou la règle doit être remplacée par un contrat directionnel (cf. ADR à venir).
- Pas de duplication de logique métier : les tools d'analyse appellent les `service.py` existants en lecture seule.
- L'audit MCP, le rate limiting par PAT, et les heuristiques de compromission ont une maison unique (`mcp/`), même si l'entité `PATToken` vit ailleurs. La frontière entre `auth/` et `mcp/` est documentée dans CONTEXT.md.
- L'expansion future (nouveaux tools, nouveaux transports MCP) se fait dans un périmètre clair, sans toucher les modules métier.
