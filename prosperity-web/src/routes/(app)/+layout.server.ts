import { redirect } from '@sveltejs/kit';
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
			redirect(303, '/login');
		}

		const user = await res.json();
		return { user };
	} catch {
		redirect(303, '/login');
	}
};
