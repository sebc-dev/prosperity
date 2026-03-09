import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

const API_URL = env.API_URL ?? 'http://localhost:8080';

export const load: PageServerLoad = async () => {
	try {
		const res = await fetch(`${API_URL}/api/setup/status`);
		if (res.ok) {
			const data = await res.json();
			if (data.adminExists) {
				redirect(303, '/login');
			}
		}
	} catch {
		// API unreachable -- show setup page anyway
	}

	return {};
};

export const actions: Actions = {
	default: async ({ request, cookies }) => {
		const form = await request.formData();
		const email = form.get('email') as string;
		const displayName = form.get('displayName') as string;
		const password = form.get('password') as string;
		const passwordConfirm = form.get('passwordConfirm') as string;

		if (!email || !displayName || !password) {
			return fail(400, { error: 'missing_fields', email, displayName });
		}

		if (password !== passwordConfirm) {
			return fail(400, { error: 'passwords_mismatch', email, displayName });
		}

		if (password.length < 8) {
			return fail(400, { error: 'password_too_short', email, displayName });
		}

		try {
			const res = await fetch(`${API_URL}/api/setup`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, displayName, password })
			});

			if (!res.ok) {
				if (res.status === 403) {
					return fail(403, { error: 'admin_exists', email, displayName });
				}
				return fail(400, { error: 'setup_failed', email, displayName });
			}

			const data = await res.json();

			cookies.set('access_token', data.accessToken, {
				path: '/',
				httpOnly: true,
				secure: true,
				sameSite: 'lax',
				maxAge: 60 * 15
			});
			cookies.set('refresh_token', data.refreshToken, {
				path: '/',
				httpOnly: true,
				secure: true,
				sameSite: 'lax',
				maxAge: 60 * 60 * 24 * 30
			});
		} catch {
			return fail(500, { error: 'server_error', email, displayName });
		}

		redirect(303, '/settings');
	}
};
