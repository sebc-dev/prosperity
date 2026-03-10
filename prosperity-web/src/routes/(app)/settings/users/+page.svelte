<script lang="ts">
	import { enhance } from '$app/forms';
	import * as m from '$lib/i18n/messages.js';

	let { data, form } = $props();

	let loading = $state(false);
	let showSuccess = $state(false);
	let showForm = $state(false);
	let email = $state('');
	let displayName = $state('');
	let password = $state('');

	$effect(() => {
		if (form?.success) {
			showSuccess = true;
			showForm = false;
			email = '';
			displayName = '';
			password = '';
			setTimeout(() => {
				showSuccess = false;
			}, 3000);
		}
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
			{m.users_title()}
		</h2>
		<button
			type="button"
			onclick={() => (showForm = !showForm)}
			class="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
		>
			{m.users_add()}
		</button>
	</div>

	{#if showSuccess}
		<div
			class="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200"
		>
			{m.users_created()}
		</div>
	{/if}

	{#if form?.error && !form?.success}
		<div
			class="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.common_error()}
		</div>
	{/if}

	<!-- Add user form -->
	{#if showForm}
		<div
			class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
		>
			<h3 class="mb-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
				{m.users_add()}
			</h3>

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
						{m.users_email()}
					</label>
					<input
						id="email"
						name="email"
						type="email"
						required
						bind:value={email}
						class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
					/>
				</div>

				<div>
					<label
						for="displayName"
						class="block text-sm font-medium text-gray-700 dark:text-gray-300"
					>
						{m.users_display_name()}
					</label>
					<input
						id="displayName"
						name="displayName"
						type="text"
						required
						bind:value={displayName}
						class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
					/>
				</div>

				<div>
					<label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						{m.users_temp_password()}
					</label>
					<input
						id="password"
						name="password"
						type="password"
						required
						minlength="8"
						bind:value={password}
						class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
					/>
					<p class="mt-1 text-sm text-amber-600 dark:text-amber-400">
						{m.users_force_change_note()}
					</p>
				</div>

				<div class="flex justify-end gap-2">
					<button
						type="button"
						onclick={() => (showForm = false)}
						class="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					>
						{m.common_cancel()}
					</button>
					<button
						type="submit"
						disabled={loading}
						class="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
					>
						{#if loading}
							{m.common_loading()}
						{:else}
							{m.users_add()}
						{/if}
					</button>
				</div>
			</form>
		</div>
	{/if}

	<!-- Users list -->
	<div class="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
		{#if data.users && data.users.length > 0}
			<div class="divide-y divide-gray-200 dark:divide-gray-800">
				{#each data.users as user (user.email)}
					<div class="flex items-center justify-between px-6 py-4">
						<div>
							<p class="text-sm font-medium text-gray-900 dark:text-gray-100">
								{user.displayName}
							</p>
							<p class="text-sm text-gray-500 dark:text-gray-400">{user.email}</p>
						</div>
						<span
							class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium {user.role ===
							'ADMIN'
								? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
								: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'}"
						>
							{user.role === 'ADMIN' ? m.users_role_admin() : m.users_role_standard()}
						</span>
					</div>
				{/each}
			</div>
		{:else}
			<div class="px-6 py-8 text-center">
				<p class="text-sm text-gray-500 dark:text-gray-400">{m.users_no_users()}</p>
			</div>
		{/if}
	</div>
</div>
