import type { RequestHandler } from 'msw'

// Handlers communs (vides au départ) ; enrichis par S14.4 (sync) et S14.6 (auth),
// en réutilisant les schémas OpenAPI. Les tests ajoutent leurs handlers ad-hoc via
// `server.use(...)`.
export const handlers: RequestHandler[] = []
