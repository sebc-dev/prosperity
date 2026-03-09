<script lang="ts">
	import { enhance } from '$app/forms';
	import * as m from '$lib/i18n/messages.js';

	let { data, form } = $props();

	let loading = $state(false);
	let showSuccess = $state(false);
	let displayName = $state(data.user?.displayName ?? '');

	$effect(() => {
		if (form?.success) {
			showSuccess = true;
			if (form.displayName) {
				displayName = form.displayName;
			}
			setTimeout(() => {
				showSuccess = false;
			}, 3000);
		}
	});
</script>

<div class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
	<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
		{m.settings_profile()}
	</h2>

	{#if showSuccess}
		<div
			class="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200"
		>
			{m.profile_updated()}
		</div>
	{/if}

	{#if form?.error}
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
				{m.profile_email()}
			</label>
			<input
				id="email"
				type="email"
				value={data.user?.email ?? ''}
				disabled
				class="mt-1 block w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
			/>
		</div>

		<div>
			<label
				for="displayName"
				class="block text-sm font-medium text-gray-700 dark:text-gray-300"
			>
				{m.profile_display_name()}
			</label>
			<input
				id="displayName"
				name="displayName"
				type="text"
				bind:value={displayName}
				required
				class="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			/>
		</div>

		<div class="flex justify-end">
			<button
				type="submit"
				disabled={loading}
				class="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200 dark:focus:ring-gray-100"
			>
				{#if loading}
					{m.common_loading()}
				{:else}
					{m.common_save()}
				{/if}
			</button>
		</div>
	</form>
</div>
