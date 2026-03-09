import { fail, redirect } from '@sveltejs/kit';
import { apiClient } from '$lib/api/client';
import type { Actions } from './$types';

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const name = form.get('name') as string;
		const bankName = form.get('bankName') as string;
		const accountType = form.get('accountType') as string;
		const currency = form.get('currency') as string;
		const initialBalance = form.get('initialBalance') as string;
		const color = form.get('color') as string;

		if (!name || !accountType) {
			return fail(400, {
				error: 'validation',
				name,
				bankName,
				accountType,
				currency,
				initialBalance,
				color
			});
		}

		const api = apiClient(locals.accessToken);

		try {
			const res = await api.post('/api/accounts', {
				name,
				bankName: bankName || '',
				accountType,
				currency: currency || 'EUR',
				initialBalance: parseFloat(initialBalance || '0'),
				color: color || '#3B82F6'
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				return fail(res.status, {
					error: 'server',
					message: data.message || '',
					name,
					bankName,
					accountType,
					currency,
					initialBalance,
					color
				});
			}
		} catch {
			return fail(500, {
				error: 'server',
				name,
				bankName,
				accountType,
				currency,
				initialBalance,
				color
			});
		}

		redirect(303, '/accounts');
	}
};
