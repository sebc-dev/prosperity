<script lang="ts">
	import { resolve } from '$app/paths';
	import * as m from '$lib/i18n/messages.js';
	import Card from '$lib/components/ui/Card.svelte';

	let { data } = $props();
</script>

<div class="space-y-6">
	<h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
		{m.dashboard_welcome({ name: data.user.displayName })}
	</h1>

	<div class="grid gap-6 md:grid-cols-2">
		<Card>
			<h2 class="mb-2 text-sm font-medium text-gray-500 dark:text-gray-400">
				{m.accounts_title()}
			</h2>
			<p class="text-sm text-gray-600 dark:text-gray-300">
				{m.dashboard_accounts_cta()}
			</p>
			<a
				href={resolve('/accounts')}
				class="mt-4 inline-flex items-center text-sm font-medium text-gray-900 hover:text-gray-700 dark:text-gray-100 dark:hover:text-gray-300"
			>
				{m.dashboard_view_accounts()}
				<svg
					class="ml-1 h-4 w-4"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
				</svg>
			</a>
		</Card>
	</div>
</div>
