# Foyer singleton + flow d'invitation token-based

Le foyer n'est jamais qu'au singulier dans l'application ("un déploiement = un foyer", §5 de la spec), mais nous avons besoin d'un anchor pour porter `base_currency` (cf. ADR 0008) et l'`initialized_at` sans introduire un état applicatif éparpillé en config. Nous décidons d'utiliser une **table `household` singleton** avec **UUID fixe** (`00000000-0000-0000-0000-000000000001`) et une **contrainte CHECK** qui interdit toute insertion d'un second foyer. Le bootstrap initial du premier admin se fait via un **flow web `/setup` lock-after-init** (route ouverte si et seulement si `users` est vide, retourne 404 ensuite), avec fallback env vars optionnel pour scénarios de restore automatisés.

Le flow d'invitation utilise un **token aléatoire hashé en DB** (pas JWT — révocation triviale, pas de signing key à gérer), **pré-attribué à un email** (anti-leak), durée 7 jours, ré-générable (nouveau token sur la même row, ancien lien invalidé). **Le rôle de l'invité est toujours `member` ; la promotion en `admin` est un acte séparé** avec audit log — un admin compromis ne peut donc pas créer directement un second admin par invitation.

## Consequences

- L'UUID fixe simplifie tous les FK qui pourraient référencer le foyer (audit logs, settings éventuels) : pas de lookup, pas de cache.
- La table `invitations` est server-only (cf. découpage des sync rules, ADR 0003) : pas de vue offline des invitations en cours pour l'admin, ce qui est acceptable (acte rare, fait en ligne).
- Le rôle figé à `member` à l'invitation introduit une étape supplémentaire pour promouvoir un nouvel admin (acceptable car rare et sécurité-positive).
- Tout post-V1 qui voudrait du multi-foyer (hors-périmètre actuel) devra ré-architecturer : la contrainte CHECK et l'UUID fixe sont des hypothèses fortes. Documenté dans hors-périmètre §5.
