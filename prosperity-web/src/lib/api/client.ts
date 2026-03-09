import { env } from '$env/dynamic/private';

const API_URL = env.API_URL ?? 'http://localhost:8080';

export function apiClient(accessToken?: string) {
	const headers: Record<string, string> = {
		'Content-Type': 'application/json'
	};

	if (accessToken) {
		headers['Authorization'] = `Bearer ${accessToken}`;
	}

	return {
		get(path: string): Promise<Response> {
			return fetch(`${API_URL}${path}`, {
				method: 'GET',
				headers
			});
		},

		post(path: string, body?: unknown): Promise<Response> {
			return fetch(`${API_URL}${path}`, {
				method: 'POST',
				headers,
				body: body != null ? JSON.stringify(body) : undefined
			});
		},

		put(path: string, body?: unknown): Promise<Response> {
			return fetch(`${API_URL}${path}`, {
				method: 'PUT',
				headers,
				body: body != null ? JSON.stringify(body) : undefined
			});
		},

		patch(path: string, body?: unknown): Promise<Response> {
			return fetch(`${API_URL}${path}`, {
				method: 'PATCH',
				headers,
				body: body != null ? JSON.stringify(body) : undefined
			});
		},

		delete(path: string): Promise<Response> {
			return fetch(`${API_URL}${path}`, {
				method: 'DELETE',
				headers
			});
		}
	};
}
