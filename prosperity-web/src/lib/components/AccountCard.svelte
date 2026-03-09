<script lang="ts">
	import * as m from '$lib/i18n/messages.js';
	import Badge from '$lib/components/ui/Badge.svelte';

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

	interface Props {
		account: Account;
	}

	let { account }: Props = $props();

	function formatCurrency(amount: number, currency: string): string {
		return new Intl.NumberFormat(undefined, {
			style: 'currency',
			currency,
			minimumFractionDigits: 2,
			maximumFractionDigits: 2
		}).format(amount);
	}
</script>

<a
	href="/accounts/{account.id}"
	class="group block overflow-hidden rounded-lg border border-gray-200 bg-white transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:shadow-gray-800/50"
>
	<!-- Color bar -->
	<div class="h-1.5" style="background-color: {account.color}"></div>

	<div class="p-5">
		<!-- Header: name + type badge -->
		<div class="mb-3 flex items-start justify-between">
			<div>
				<h3 class="font-semibold text-gray-900 dark:text-gray-100">{account.name}</h3>
				<p class="mt-0.5 text-sm text-gray-500 dark:text-gray-400">{account.bankName}</p>
			</div>
			<Badge variant={account.accountType === 'PERSONAL' ? 'default' : 'info'}>
				{account.accountType === 'PERSONAL'
					? m.accounts_form_type_personal()
					: m.accounts_form_type_shared()}
			</Badge>
		</div>

		<!-- Dual balance -->
		<div class="grid grid-cols-2 gap-4">
			<div>
				<p class="text-xs font-medium text-gray-500 dark:text-gray-400">
					{m.accounts_balance_real()}
				</p>
				<p class="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
					{formatCurrency(account.currentBalance, account.currency)}
				</p>
			</div>
			<div>
				<p class="text-xs font-medium text-gray-500 dark:text-gray-400">
					{m.accounts_balance_projected()}
				</p>
				<p class="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
					{formatCurrency(account.projectedBalance, account.currency)}
				</p>
			</div>
		</div>
	</div>
</a>
