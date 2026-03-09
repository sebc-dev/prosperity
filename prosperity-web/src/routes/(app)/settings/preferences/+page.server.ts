import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { apiClient } from '$lib/api/client';

export const load: PageServerLoad = async ({ locals }) => {
	const api = apiClient(locals.accessToken);

	// Fetch user preferences and categories in parallel
	const [prefsRes, categoriesRes] = await Promise.all([
		api.get('/api/users/me/profile'),
		api.get('/api/categories')
	]);

	let preferences = { theme: 'system', defaultCurrency: 'EUR', language: 'fr', favoriteCategories: [] as string[] };
	let categories: Array<{ id: string; nameKey: string; icon: string }> = [];

	if (prefsRes.ok) {
		const userData = await prefsRes.json();
		if (userData.preferences) {
			const prefs = typeof userData.preferences === 'string' ? JSON.parse(userData.preferences) : userData.preferences;
			preferences = {
				theme: prefs.theme ?? 'system',
				defaultCurrency: prefs.defaultCurrency ?? 'EUR',
				language: prefs.language ?? 'fr',
				favoriteCategories: prefs.favoriteCategories ?? []
			};
		}
	}

	if (categoriesRes.ok) {
		categories = await categoriesRes.json();
	}

	return { preferences, categories };
};

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const theme = form.get('theme') as string;
		const defaultCurrency = form.get('defaultCurrency') as string;
		const language = form.get('language') as string;
		const favoriteCategories = form.getAll('favoriteCategories') as string[];

		try {
			const api = apiClient(locals.accessToken);
			const res = await api.patch('/api/users/me/preferences', {
				theme: theme || 'system',
				defaultCurrency: defaultCurrency || 'EUR',
				language: language || 'fr',
				favoriteCategories
			});

			if (!res.ok) {
				return fail(res.status, { error: 'update_failed' });
			}

			return { success: true };
		} catch {
			return fail(500, { error: 'server_error' });
		}
	}
};
