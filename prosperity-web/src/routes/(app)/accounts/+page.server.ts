import { apiClient } from '$lib/api/client';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const api = apiClient(locals.accessToken);
	const res = await api.get('/api/accounts');

	if (!res.ok) {
		return { accounts: [] };
	}

	const accounts = await res.json();
	return { accounts };
};
