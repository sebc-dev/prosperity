import { error, fail, isHttpError, isRedirect, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { apiClient } from '$lib/api/client';

export const load: PageServerLoad = async ({ parent, locals }) => {
	const { user } = await parent();

	// Redirect non-admin users
	if (user?.role !== 'ADMIN') {
		redirect(303, '/settings/profile');
	}

	try {
		const api = apiClient(locals.accessToken);
		const res = await api.get('/api/users');

		if (!res.ok) {
			if (res.status === 401) {
				redirect(303, '/login');
			}
			error(res.status, 'Failed to load users');
		}

		const users = await res.json();
		return { users };
	} catch (e) {
		if (isRedirect(e) || isHttpError(e)) {
			throw e;
		}
		error(503, 'Service temporarily unavailable');
	}
};

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const api = apiClient(locals.accessToken);
		const meRes = await api.get('/api/users/me');
		if (!meRes.ok || (await meRes.json()).role !== 'ADMIN') {
			return fail(403, { error: 'Forbidden' });
		}

		const form = await request.formData();
		const email = form.get('email') as string;
		const displayName = form.get('displayName') as string;
		const password = form.get('password') as string;

		if (!email?.trim() || !displayName?.trim() || !password?.trim()) {
			return fail(400, { error: 'missing_fields', email, displayName });
		}

		if (password.length < 8) {
			return fail(400, { error: 'password_too_short', email, displayName });
		}

		try {
			const res = await api.post('/api/users', {
				email: email.trim(),
				displayName: displayName.trim(),
				password
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				return fail(res.status, {
					error: data.message ?? 'create_failed',
					email,
					displayName
				});
			}

			return { success: true };
		} catch {
			return fail(500, { error: 'server_error', email, displayName });
		}
	}
};
