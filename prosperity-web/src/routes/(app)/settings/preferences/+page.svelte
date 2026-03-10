<script lang="ts">
	import { enhance } from '$app/forms';
	import * as m from '$lib/i18n/messages.js';
	import { preferences } from '$lib/stores/preferences.svelte';

	let { data, form } = $props();

	let loading = $state(false);
	let showSuccess = $state(false);

	let theme = $state(data.preferences?.theme ?? 'system');
	let defaultCurrency = $state(data.preferences?.defaultCurrency ?? 'EUR');
	let language = $state(data.preferences?.language ?? 'fr');
	let favoriteCategories = $state<string[]>(data.preferences?.favoriteCategories ?? []);

	const currencies = ['EUR', 'USD', 'GBP', 'CHF', 'CAD'];

	function setTheme(value: 'light' | 'dark' | 'system') {
		theme = value;
		preferences.setTheme(value);
	}

	function toggleCategory(categoryId: string) {
		if (favoriteCategories.includes(categoryId)) {
			favoriteCategories = favoriteCategories.filter((c) => c !== categoryId);
		} else {
			favoriteCategories = [...favoriteCategories, categoryId];
		}
	}

	$effect(() => {
		if (form?.success) {
			showSuccess = true;
			setTimeout(() => {
				showSuccess = false;
			}, 3000);
		}
	});
</script>

<div class="space-y-6">
	{#if showSuccess}
		<div
			class="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200"
		>
			{m.preferences_updated()}
		</div>
	{/if}

	{#if form?.error}
		<div
			class="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
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
		class="space-y-6"
	>
		<!-- Theme -->
		<div
			class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
		>
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
				{m.preferences_theme()}
			</h2>
			<input type="hidden" name="theme" value={theme} />
			<div class="flex gap-2">
				{#each [{ value: 'light', label: m.theme_light() }, { value: 'dark', label: m.theme_dark() }, { value: 'system', label: m.theme_system() }] as option}
					<button
						type="button"
						onclick={() => setTheme(option.value as 'light' | 'dark' | 'system')}
						class="rounded-md px-4 py-2 text-sm font-medium transition-colors {theme ===
						option.value
							? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
							: 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
					>
						{option.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Currency -->
		<div
			class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
		>
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
				{m.currency_default()}
			</h2>
			<select
				name="defaultCurrency"
				bind:value={defaultCurrency}
				class="block w-full max-w-xs rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			>
				{#each currencies as currency}
					<option value={currency}>{currency}</option>
				{/each}
			</select>
		</div>

		<!-- Language -->
		<div
			class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
		>
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
				{m.language_label()}
			</h2>
			<select
				name="language"
				bind:value={language}
				class="block w-full max-w-xs rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-gray-100 dark:focus:ring-gray-100"
			>
				<option value="fr">Francais</option>
				<option value="en">English</option>
			</select>
		</div>

		<!-- Favorite Categories -->
		<div
			class="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
		>
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
				{m.preferences_favorite_categories()}
			</h2>
			{#if data.categories && data.categories.length > 0}
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
					{#each data.categories as category}
						<label
							class="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors {favoriteCategories.includes(
								category.id
							)
								? 'border-gray-900 bg-gray-50 text-gray-900 dark:border-gray-100 dark:bg-gray-800 dark:text-gray-100'
								: 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-gray-700 dark:text-gray-400 dark:hover:border-gray-600'}"
						>
							<input
								type="checkbox"
								name="favoriteCategories"
								value={category.id}
								checked={favoriteCategories.includes(category.id)}
								onchange={() => toggleCategory(category.id)}
								class="sr-only"
							/>
							{#if category.icon}
								<span>{category.icon}</span>
							{/if}
							<span>{category.nameKey}</span>
						</label>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-gray-500 dark:text-gray-400">{m.preferences_no_categories()}</p>
			{/if}
		</div>

		<!-- Save button -->
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
