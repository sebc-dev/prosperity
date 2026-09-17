Pas d'impact sécurité.

Le change n'ajoute ni entrée externe, ni endpoint, ni permission, ni traitement de données, ni
dépendance (dev ou prod) : une règle de lint dans une config existante et deux tests unitaires qui
lisent des fichiers du dépôt. Effet indirect favorable : A10 borne à `client/src/lib` la surface qui
parle au réseau, donc l'endroit où le Bearer est injecté (`lib/auth/session`) — c'est déjà l'état du
code, la garde empêche qu'il dérive.
