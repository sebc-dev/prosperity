<script lang="ts">
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import * as m from '$lib/i18n/messages.js';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import ColorPicker from '$lib/components/ui/ColorPicker.svelte';

	let { form } = $props();

	let loading = $state(false);
	let name = $state(form?.name ?? '');
	let bankName = $state(form?.bankName ?? '');
	let accountType = $state(form?.accountType ?? 'PERSONAL');
	let currency = $state(form?.currency ?? 'EUR');
	let initialBalance = $state(form?.initialBalance ?? '0');
	let color = $state(form?.color ?? '#3B82F6');

	const typeOptions = [
		{ value: 'PERSONAL', label: m.accounts_form_type_personal() },
		{ value: 'SHARED', label: m.accounts_form_type_shared() }
	];

	const currencyOptions = [
		{ value: 'EUR', label: 'EUR - Euro' },
		{ value: 'USD', label: 'USD - US Dollar' },
		{ value: 'GBP', label: 'GBP - British Pound' },
		{ value: 'CHF', label: 'CHF - Swiss Franc' },
		{ value: 'CAD', label: 'CAD - Canadian Dollar' },
		{ value: 'MAD', label: 'MAD - Moroccan Dirham' },
		{ value: 'TND', label: 'TND - Tunisian Dinar' },
		{ value: 'DZD', label: 'DZD - Algerian Dinar' }
	];
</script>

<div class="mx-auto max-w-lg space-y-6">
	<!-- Header -->
	<div>
		<a
			href={resolve('/accounts')}
			class="mb-4 inline-flex items-center text-sm text-gray-500 transition-colors hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
		>
			<svg
				class="mr-1 h-4 w-4"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			{m.common_back()}
		</a>
		<h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
			{m.accounts_create()}
		</h1>
	</div>

	{#if form?.error === 'server'}
		<div
			class="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
		>
			{m.accounts_form_error()}
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
		class="space-y-5"
	>
		<Input
			label={m.accounts_form_name()}
			name="name"
			placeholder={m.accounts_form_name_placeholder()}
			required
			bind:value={name}
		/>

		<Input
			label={m.accounts_form_bank()}
			name="bankName"
			placeholder={m.accounts_form_bank_placeholder()}
			bind:value={bankName}
		/>

		<Select
			label={m.accounts_form_type()}
			name="accountType"
			options={typeOptions}
			required
			bind:value={accountType}
		/>

		<Select
			label={m.accounts_form_currency()}
			name="currency"
			options={currencyOptions}
			bind:value={currency}
		/>

		<Input
			label={m.accounts_form_initial_balance()}
			name="initialBalance"
			type="number"
			step="0.01"
			bind:value={initialBalance}
		/>

		<ColorPicker label={m.accounts_form_color()} name="color" bind:value={color} />

		<div class="flex gap-3 pt-2">
			<Button type="submit" variant="primary" {loading}>
				{m.accounts_form_submit()}
			</Button>
			<a href={resolve('/accounts')}>
				<Button type="button" variant="secondary">
					{m.common_cancel()}
				</Button>
			</a>
		</div>
	</form>
</div>
