<script lang="ts">
	import * as m from '$lib/i18n/messages.js';
	import Button from '$lib/components/ui/Button.svelte';
	import AccountCard from '$lib/components/AccountCard.svelte';

	let { data } = $props();

	interface Account {
		id: string;
		name: string;
		bankName: string;
		accountType: 'PERSONAL' | 'SHARED';
		currency: string;
		currentBalance: number;
		projectedBalance: number;
		color: string;
	}

	let personalAccounts = $derived(
		(data.accounts as Account[]).filter((a) => a.accountType === 'PERSONAL')
	);
	let sharedAccounts = $derived(
		(data.accounts as Account[]).filter((a) => a.accountType === 'SHARED')
	);
	let hasAccounts = $derived((data.accounts as Account[]).length > 0);
</script>

<div class="space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
			{m.accounts_title()}
		</h1>
		<a href="/accounts/new">
			<Button variant="primary" size="md">
				{m.accounts_create()}
			</Button>
		</a>
	</div>

	{#if !hasAccounts}
		<!-- Empty state -->
		<div
			class="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 px-6 py-16 dark:border-gray-700"
		>
			<svg
				class="mb-4 h-12 w-12 text-gray-400 dark:text-gray-500"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="1"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z"
				/>
			</svg>
			<h3 class="mb-1 text-lg font-medium text-gray-900 dark:text-gray-100">
				{m.accounts_empty_title()}
			</h3>
			<p class="mb-6 text-sm text-gray-500 dark:text-gray-400">
				{m.accounts_empty_description()}
			</p>
			<a href="/accounts/new">
				<Button variant="primary">
					{m.accounts_empty_cta()}
				</Button>
			</a>
		</div>
	{:else}
		<!-- Personal accounts section -->
		{#if personalAccounts.length > 0}
			<section>
				<h2 class="mb-4 text-lg font-medium text-gray-900 dark:text-gray-100">
					{m.accounts_personal()}
				</h2>
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each personalAccounts as account (account.id)}
						<AccountCard {account} />
					{/each}
				</div>
			</section>
		{/if}

		<!-- Shared accounts section -->
		{#if sharedAccounts.length > 0}
			<section>
				<h2 class="mb-4 text-lg font-medium text-gray-900 dark:text-gray-100">
					{m.accounts_shared()}
				</h2>
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each sharedAccounts as account (account.id)}
						<AccountCard {account} />
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>
