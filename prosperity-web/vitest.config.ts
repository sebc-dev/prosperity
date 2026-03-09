import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
	plugins: [svelte({ hot: false })],

	test: {
		include: ['src/**/*.test.ts'],
		environment: 'jsdom',
		globals: true,
		alias: {
			$lib: new URL('./src/lib', import.meta.url).pathname,
			'$app/forms': new URL('./src/test-mocks/app-forms.ts', import.meta.url).pathname,
			'$app/state': new URL('./src/test-mocks/app-state.ts', import.meta.url).pathname,
			'$env/dynamic/private': new URL('./src/test-mocks/env.ts', import.meta.url).pathname
		}
	},

	resolve: {
		conditions: ['browser']
	}
});
