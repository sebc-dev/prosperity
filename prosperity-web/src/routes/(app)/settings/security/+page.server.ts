import { fail } from '@sveltejs/kit';
import type { Actions } from './$types';
import { apiClient } from '$lib/api/client';

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const oldPassword = form.get('oldPassword') as string;
		const newPassword = form.get('newPassword') as string;
		const confirmPassword = form.get('confirmPassword') as string;

		if (!oldPassword || !newPassword || !confirmPassword) {
			return fail(400, { error: 'missing_fields' });
		}

		if (newPassword.length < 8) {
			return fail(400, { error: 'password_too_short' });
		}

		if (newPassword !== confirmPassword) {
			return fail(400, { error: 'password_mismatch' });
		}

		try {
			const api = apiClient(locals.accessToken);
			const res = await api.post('/api/users/me/password', {
				oldPassword,
				newPassword
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				return fail(res.status, { error: data.message ?? 'change_failed' });
			}

			return { success: true };
		} catch {
			return fail(500, { error: 'server_error' });
		}
	}
};
