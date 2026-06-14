// @vitest-environment jsdom
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'

import { api } from '@/lib/api/client'
import { server } from '@tests/msw/server'

// Smoke runtime du client généré : prouve que `baseUrl` + le path typé câblent une VRAIE
// requête interceptée par MSW. `onUnhandledRequest:'error'` (tests/setup) garantit qu'un
// mauvais path échouerait le test (anti faux-vert). La garantie TYPE-LEVEL (la réponse expose
// `access_token`/`refresh_token`) vit dans `schema.assert.ts`, compilée par `npm run build`.
// L'idempotence de la génération est vérifiée par `npm run gen:api:check` (CI, S14.7).
test('api.POST(/auth/login) émet une requête typée interceptée → TokenPair', async () => {
  server.use(
    http.post('http://localhost:8000/auth/login', () =>
      HttpResponse.json({
        access_token: 'access.jwt.sig',
        refresh_token: 'rt-opaque',
        token_type: 'bearer',
      }),
    ),
  )

  const { data, error } = await api.POST('/auth/login', {
    body: { email: 'a@b.c', password: 'pw' },
  })

  expect(error).toBeUndefined()
  expect(data?.access_token).toBe('access.jwt.sig')
  expect(data?.refresh_token).toBe('rt-opaque')
})
