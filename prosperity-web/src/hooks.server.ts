import { redirect, type Handle } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { env } from '$env/dynamic/private';

const API_URL = env.API_URL ?? 'http://localhost:8080';

const PUBLIC_PATHS = ['/login', '/setup'];

function isPublicPath(pathname: string): boolean {
	return PUBLIC_PATHS.some((p) => pathname.startsWith(p));
}

const tokenRefresh: Handle = async ({ event, resolve }) => {
	const accessToken = event.cookies.get('access_token');
	const refreshToken = event.cookies.get('refresh_token');

	if (!accessToken && refreshToken) {
		try {
			const res = await fetch(`${API_URL}/api/auth/refresh`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ refreshToken })
			});

			if (res.ok) {
				const data = await res.json();
				event.cookies.set('access_token', data.accessToken, {
					path: '/',
					httpOnly: true,
					secure: true,
					sameSite: 'lax',
					maxAge: 60 * 15 // 15 minutes
				});
				event.cookies.set('refresh_token', data.refreshToken, {
					path: '/',
					httpOnly: true,
					secure: true,
					sameSite: 'lax',
					maxAge: 60 * 60 * 24 * 30 // 30 days
				});
				event.locals.accessToken = data.accessToken;
			} else {
				// Refresh failed -- clear cookies and redirect with expired flag
				event.cookies.delete('access_token', { path: '/' });
				event.cookies.delete('refresh_token', { path: '/' });
				if (!isPublicPath(event.url.pathname)) {
					redirect(303, '/login?expired=true');
				}
			}
		} catch {
			// API unreachable -- clear cookies silently
			event.cookies.delete('access_token', { path: '/' });
			event.cookies.delete('refresh_token', { path: '/' });
		}
	}

	return resolve(event);
};

const authGuard: Handle = async ({ event, resolve }) => {
	const accessToken = event.cookies.get('access_token') ?? event.locals.accessToken;

	if (!accessToken && !isPublicPath(event.url.pathname)) {
		redirect(303, '/login');
	}

	if (accessToken) {
		event.locals.accessToken = accessToken;
	}

	return resolve(event);
};

export const handle = sequence(tokenRefresh, authGuard);
