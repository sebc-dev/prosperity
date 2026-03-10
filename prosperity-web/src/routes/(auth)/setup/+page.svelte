<script lang="ts">
	import { enhance } from '$app/forms';
	import * as m from '$lib/i18n/messages.js';

	let { form } = $props();

	let loading = $state(false);
	let password = $state('');
	let passwordConfirm = $state('');

	let passwordsMatch = $derived(password === passwordConfirm || passwordConfirm === '');
	let passwordLongEnough = $derived(password.length >= 8 || password === '');
</script>

<div class="rounded-lg border border-gray-200 bg-white p-8 dark:border-gray-800 dark:bg-gray-900">
	<div class="mb-6 text-center">
		<h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
			Prosperity
		</h1>
		<p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
			{m.setup_description()}
		</p>
	</div>

	{#if form?.error === 'passwords_mismatch'}
		<div
			class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.security_password_mismatch()}
		</div>
	{:else if form?.error === 'password_too_short'}
		<div
			class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.security_password_too_short()}
		</div>
	{:else if form?.error === 'admin_exists'}
		<div
			class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.setup_error_admin_exists()}
		</div>
	{:else if form?.error}
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
			<label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.setup_email()}
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
			<label for="displayName" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.setup_display_name()}
			</label>
			<input
				id="displayName"
				name="displayName"
				type="text"
				autocomplete="name"
				required
				value={form?.displayName ?? ''}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
		</div>

		<div>
			<label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
				{m.setup_password()}
			</label>
			<input
				id="password"
				name="password"
				type="password"
				autocomplete="new-password"
				required
				minlength="8"
				bind:value={password}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-gray-100 dark:focus:ring-gray-100"
				class:border-red-500={!passwordLongEnough}
			/>
			{#if !passwordLongEnough}
				<p class="mt-1 text-xs text-red-600 dark:text-red-400">
					{m.security_password_too_short()}
				</p>
			{/if}
		</div>

		<div>
			<label
				for="passwordConfirm"
				class="block text-sm font-medium text-gray-700 dark:text-gray-300"
			>
				{m.setup_password_confirm()}
			</label>
			<input
				id="passwordConfirm"
				name="passwordConfirm"
				type="password"
				autocomplete="new-password"
				required
				minlength="8"
				bind:value={passwordConfirm}
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-gray-100 dark:focus:ring-gray-100"
				class:border-red-500={!passwordsMatch}
			/>
			{#if !passwordsMatch}
				<p class="mt-1 text-xs text-red-600 dark:text-red-400">{m.security_password_mismatch()}</p>
			{/if}
		</div>

		<button
			type="submit"
			disabled={loading || !passwordsMatch || !passwordLongEnough}
			class="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
		>
			{#if loading}
				{m.common_loading()}
			{:else}
				{m.setup_submit()}
			{/if}
		</button>
	</form>
</div>
