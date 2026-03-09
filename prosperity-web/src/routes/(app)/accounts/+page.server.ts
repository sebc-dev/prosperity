import { error, isHttpError, isRedirect, redirect } from '@sveltejs/kit';
import { apiClient } from '$lib/api/client';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	try {
		const api = apiClient(locals.accessToken);
		const res = await api.get('/api/accounts');

		if (!res.ok) {
			if (res.status === 401) {
				redirect(303, '/login');
			}
			error(res.status, 'Failed to load accounts');
		}

		const accounts = await res.json();
		return { accounts };
	} catch (e) {
		if (isRedirect(e) || isHttpError(e)) {
			throw e;
		}
		error(503, 'Service temporarily unavailable');
	}
};
