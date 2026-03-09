import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

const API_URL = env.API_URL ?? 'http://localhost:8080';

export const load: PageServerLoad = async ({ cookies }) => {
	const accessToken = cookies.get('access_token');
	if (accessToken) {
		redirect(303, '/');
	}

	// Check if admin exists -- if not, redirect to setup
	try {
		const res = await fetch(`${API_URL}/api/setup/status`);
		if (res.ok) {
			const data = await res.json();
			if (!data.adminExists) {
				redirect(303, '/setup');
			}
		}
	} catch {
		// API unreachable -- show login page anyway
	}

	return {};
};

export const actions: Actions = {
	default: async ({ request, cookies }) => {
		const form = await request.formData();
		const email = form.get('email') as string;
		const password = form.get('password') as string;

		if (!email || !password) {
			return fail(400, { error: 'invalid_credentials', email });
		}

		try {
			const res = await fetch(`${API_URL}/api/auth/login`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});

			if (!res.ok) {
				return fail(400, { error: 'invalid_credentials', email });
			}

			const data = await res.json();

			cookies.set('access_token', data.accessToken, {
				path: '/',
				httpOnly: true,
				secure: true,
				sameSite: 'lax',
				maxAge: 60 * 15 // 15 minutes
			});
			cookies.set('refresh_token', data.refreshToken, {
				path: '/',
				httpOnly: true,
				secure: true,
				sameSite: 'lax',
				maxAge: 60 * 60 * 24 * 30 // 30 days
			});
		} catch {
			return fail(500, { error: 'server_error', email });
		}

		redirect(303, '/');
	}
};
