import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react-swc'
import tsconfigPaths from 'vite-tsconfig-paths'
import { defineConfig } from 'vitest/config'

// Une seule version de Vite (override `vite: $vite` dans package.json) → `vitest/config`
// et les plugins sont typés contre le même vite@6 (sinon clash PluginOption v5/v6).

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
    react(),
    tsconfigPaths(),
  ],
  test: {
    environment: 'jsdom',
    // Origine stable : les requêtes relatives sont résolues contre cette URL (les
    // tests/probe utilisent `new URL(path, location.origin)` → MSW intercepte une
    // URL absolue, condition de l'interception sous le `fetch` Node/undici de jsdom).
    environmentOptions: { jsdom: { url: 'http://localhost:5173' } },
    globals: true,
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
