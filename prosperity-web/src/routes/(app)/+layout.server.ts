import { error, isHttpError, isRedirect, redirect } from '@sveltejs/kit';
import { apiClient } from '$lib/api/client';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals }) => {
	if (!locals.accessToken) {
		redirect(303, '/login');
	}

	try {
		const api = apiClient(locals.accessToken);
		const res = await api.get('/api/users/me');

		if (!res.ok) {
			if (res.status === 401) {
				redirect(303, '/login');
			}
			error(res.status, 'Failed to load user profile');
		}

		const user = await res.json();
		return { user };
	} catch (e) {
		if (isRedirect(e) || isHttpError(e)) {
			throw e;
		}
		error(503, 'Service temporarily unavailable');
	}
};
