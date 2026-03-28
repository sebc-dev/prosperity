# ADR-0002 : Architecture layered par feature (remplacement hexagonal)

## Statut
Accepte -- 2026-03-28

## Contexte
L'architecture initiale prevoyait une approche hexagonale allegee (Domain / Application / Infrastructure avec ports et adapters). A l'analyse, cette approche est sur-dimensionnee pour un monolithe personnel :
- Chaque port n'a qu'un seul adapter (un seul type de DB, un seul framework web)
- Le boilerplate ports/adapters n'apporte pas de benefice testabilite reel vs Spring Data (deja une interface)
- Le projet est aussi une vitrine technique : montrer du discernement architectural (savoir quand NE PAS abstraire) est plus credible que de l'hexagonal systematique

## Decision

Architecture **layered classique organisee par feature** avec abstraction strategique :

1. **Package-by-feature** : chaque domaine metier (account, transaction, envelope...) est un package contenant controller, service, repository, entite
2. **Pas de ports/adapters generalises** : les services appellent directement les repositories Spring Data JPA et les controllers Spring MVC
3. **Abstraction uniquement sur le connecteur bancaire** : interface `BankConnector` avec implementation `PlaidBankConnector` -- seul cas ou l'interchangeabilite est une contrainte reelle
4. **Value Objects** : Money (BigDecimal), TransactionState (enum) expriment les regles metier sans la ceremonie DDD complete

## Alternatives considerees
| Alternative | Rejetee car |
|-------------|-------------|
| Hexagonale complete (ports/adapters partout) | Over-engineering pour un monolithe avec un seul adapter par port |
| Hexagonale allegee (version originale) | Meme probleme en moins prononce, mais toujours du boilerplate sans justification |
| Vertical slices (MediatR-style) | Pattern plus .NET que Java/Spring, moins idiomatique |

## Consequences

### Positives
- Moins de boilerplate, iteration plus rapide
- Structure idiomatique Spring Boot, familiere pour tout dev Java
- Montre du discernement architectural (abstraction justifiee vs systematique)
- Package-by-feature facilite la navigation et la comprehension

### Negatives / Trade-offs
- Si un deuxieme type de persistance etait necessaire, il faudrait refactorer (tres improbable)
- Les services sont couples a Spring Data -- acceptable pour un monolithe
