// Passe séparée et advisory (CLAUDE.md §10.2) : eslint-plugin-security est bruyant, il n'entre jamais
// dans la configuration bloquante (eslint.config.mjs) ni dans le verdict de la gate.
import { defineConfig } from 'eslint/config';
import security from 'eslint-plugin-security';
import tseslint from 'typescript-eslint';

export default defineConfig(
  {
    // Mêmes exclusions que eslint.config.mjs.
    ignores: [
      'reports/**',
      'coverage/**',
      '.stryker-tmp/**',
      'node_modules/**',
      'semgrep/**',
      '.claude/**',
    ],
  },
  {
    files: ['src/**/*.ts', 'quality/**/*.ts'],
    extends: [security.configs.recommended],
    languageOptions: { parser: tseslint.parser },
  },
);
