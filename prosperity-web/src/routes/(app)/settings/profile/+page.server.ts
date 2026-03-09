import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { apiClient } from '$lib/api/client';

export const load: PageServerLoad = async ({ parent }) => {
	const { user } = await parent();
	return { user };
};

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const displayName = form.get('displayName') as string;

		if (!displayName?.trim()) {
			return fail(400, { error: 'display_name_required', displayName });
		}

		try {
			const api = apiClient(locals.accessToken);
			const res = await api.patch('/api/users/me/profile', { displayName: displayName.trim() });

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				return fail(res.status, { error: data.message ?? 'update_failed', displayName });
			}

			return { success: true, displayName: displayName.trim() };
		} catch {
			return fail(500, { error: 'server_error', displayName });
		}
	}
};
