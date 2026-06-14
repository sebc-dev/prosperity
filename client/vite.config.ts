import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Une seule version de Vite (override `vite: $vite` dans package.json) → `vitest/config`
// et les plugins sont typés contre le même vite@8 (sinon clash PluginOption).

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    // Le plugin TanStack doit précéder react() : il génère `src/routeTree.gen.ts`
    // (file-based, routesDirectory = src/pages) avant la transformation React.
    tanstackRouter({
      target: 'react',
      routesDirectory: './src/pages',
      generatedRouteTree: './src/routeTree.gen.ts',
      // Les tests co-localisés sous src/pages ne sont pas des routes → on les exclut du
      // scan pour éviter les warnings « does not export a Route » à chaque build.
      routeFileIgnorePattern: '\\.test\\.tsx?$',
    }),
    // Tailwind 4 via le plugin Vite officiel (CSS-first, pas de postcss.config) :
    // `@import "tailwindcss"` dans src/index.css suffit (D1).
    tailwindcss(),
    react(),
  ],
  // Résolution des `paths` tsconfig (`@/*`, `@tests/*`) native à Vite 8 (remplace
  // `vite-tsconfig-paths`) ; héritée par Vitest.
  resolve: { tsconfigPaths: true },
  // PowerSync Web (S14.4) charge SQLite (wa-sqlite) dans un Web Worker qui fait du
  // code-splitting (import dynamique du wasm) → format ES obligatoire (le défaut `iife`
  // ne supporte pas le code-splitting). `optimizeDeps.exclude` évite que esbuild pré-bundle
  // le SDK (worker/wasm) en dev. Cf. guide PowerSync + Vite.
  worker: { format: 'es' },
  optimizeDeps: { exclude: ['@powersync/web'] },
  test: {
    environment: 'jsdom',
    // Origine stable : les requêtes relatives sont résolues contre cette URL (les
    // tests/probe utilisent `new URL(path, location.origin)` → MSW intercepte une
    // URL absolue, condition de l'interception sous le `fetch` Node/undici de jsdom).
    environmentOptions: { jsdom: { url: 'http://localhost:5173' } },
    globals: true,
    // Base API du client typé (`lib/api/client.ts`) figée pour les tests : `import.meta.env`
    // n'est pas alimenté par `.env` sous Vitest, et `openapi-fetch` exige une URL ABSOLUE
    // (le `fetch` Node/undici de jsdom rejette un path relatif). Aligné sur le `http://localhost:8000`
    // des handlers MSW auth (et du test sync existant). Les routes auth/setup y sont interceptées.
    env: { VITE_API_BASE_URL: 'http://localhost:8000' },
    setupFiles: ['./tests/setup.ts'],
    // Tests co-localisés (src) + self-tests du harness (tests/, ex. verrou MSW).
    include: ['src/**/*.test.{ts,tsx}', 'tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      // Seuls les périmètres chiffrés par la stratégie §10 sont mesurés ; `lib/`
      // est volontairement hors mesure ici (cible rouverte en S14.4).
      include: ['src/components/business/**', 'src/features/**'],
      // TODO(S14.7) — activer ces seuils dans la CI quand les dossiers se peuplent :
      // thresholds: {
      //   'src/components/business/**': { lines: 75 },
      //   'src/features/**': { lines: 65 },
      // },
    },
  },
})
