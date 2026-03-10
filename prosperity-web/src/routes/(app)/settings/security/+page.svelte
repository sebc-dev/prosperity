<script lang="ts">
	import { enhance } from '$app/forms';
	import * as m from '$lib/i18n/messages.js';

	let { form } = $props();

	let loading = $state(false);
	let showSuccess = $state(false);
	let oldPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');

	const passwordTooShort = $derived(newPassword.length > 0 && newPassword.length < 8);
	const passwordMismatch = $derived(confirmPassword.length > 0 && newPassword !== confirmPassword);

	$effect(() => {
		if (form?.success) {
			showSuccess = true;
			oldPassword = '';
			newPassword = '';
			confirmPassword = '';
			setTimeout(() => {
				showSuccess = false;
			}, 3000);
		}
	});
</script>

<div class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
	<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
		{m.security_title()}
	</h2>

	{#if showSuccess}
		<div
			class="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200"
		>
			{m.security_password_changed()}
		</div>
	{/if}

	{#if form?.error && !form?.success}
		<div
			class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.common_error()}
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
			<label for="oldPassword" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.security_old_password()}
			</label>
			<input
				id="oldPassword"
				name="oldPassword"
				type="password"
				autocomplete="current-password"
				required
				bind:value={oldPassword}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
		</div>

		<div>
			<label for="newPassword" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.security_new_password()}
			</label>
			<input
				id="newPassword"
				name="newPassword"
				type="password"
				autocomplete="new-password"
				required
				minlength="8"
				bind:value={newPassword}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
			{#if passwordTooShort}
				<p class="mt-1 text-sm text-red-600 dark:text-red-400">
					{m.security_password_too_short()}
				</p>
			{/if}
		</div>

		<div>
			<label
				for="confirmPassword"
				class="block text-sm font-medium text-gray-700 dark:text-gray-300"
			>
				{m.security_confirm_password()}
			</label>
			<input
				id="confirmPassword"
				name="confirmPassword"
				type="password"
				autocomplete="new-password"
				required
				bind:value={confirmPassword}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
			{#if passwordMismatch}
				<p class="mt-1 text-sm text-red-600 dark:text-red-400">
					{m.security_password_mismatch()}
				</p>
			{/if}
		</div>

		<div class="flex justify-end">
			<button
				type="submit"
				disabled={loading || passwordTooShort || passwordMismatch}
				class="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
			>
				{#if loading}
					{m.common_loading()}
				{:else}
					{m.security_change_password()}
				{/if}
			</button>
		</div>
	</form>
</div>
