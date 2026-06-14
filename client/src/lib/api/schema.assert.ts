// Garantie type-level du client généré, compilée par `tsc --noEmit` (`npm run build`) — pas de
// runtime, pas de nouvelle commande. Échoue le build si la génération OpenAPI ne capte plus
// `TokenPair` (`access_token` / `refresh_token`) sur `POST /auth/login` : un garde-fou contre
// une régénération silencieusement cassée (renommage backend, drift de schéma).
import type { paths } from './schema'

type LoginOk = paths['/auth/login']['post']['responses'][200]['content']['application/json']
type Assert<T extends true> = T

// `access_token` & `refresh_token` doivent exister et être des `string`.
export type _LoginTokenPairCheck = Assert<
  LoginOk extends { access_token: string; refresh_token: string } ? true : false
>
