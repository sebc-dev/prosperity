<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import * as m from '$lib/i18n/messages.js';

	let { form } = $props();

	let loading = $state(false);
	let showExpiredToast = $state(false);

	// Check for expired session query param
	$effect(() => {
		if (page.url.searchParams.get('expired') === 'true') {
			showExpiredToast = true;
			setTimeout(() => {
				showExpiredToast = false;
			}, 5000);
		}
	});
</script>

<div class="rounded-lg border border-gray-200 bg-white p-8 dark:border-gray-800 dark:bg-gray-900">
	<div class="mb-8 text-center">
		<h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
			Prosperity
		</h1>
	</div>

	{#if showExpiredToast}
		<div
			class="mb-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
		>
			{m.session_expired()}
		</div>
	{/if}

	{#if form?.error === 'invalid_credentials'}
		<div
			class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.login_error_invalid()}
		</div>
	{/if}

	<form
		method="POST"
		use:enhance={() => {
			loading = true;
			return async ({ update }) => {
				loading = false;
				await update();
			};
		}}
		class="space-y-4"
	>
		<div>
			<label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.login_email()}
			</label>
			<input
				id="email"
				name="email"
				type="email"
				autocomplete="email"
				required
				value={form?.email ?? ''}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
		</div>

		<div>
			<label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.login_password()}
			</label>
			<input
				id="password"
				name="password"
				type="password"
				autocomplete="current-password"
				required
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
		</div>

		<button
			type="submit"
			disabled={loading}
			class="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
		>
			{#if loading}
				{m.common_loading()}
			{:else}
				{m.login_submit()}
			{/if}
		</button>
	</form>
</div>
