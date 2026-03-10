<script lang="ts">
	import { page } from '$app/state';
	import * as m from '$lib/i18n/messages.js';

	let { children, data } = $props();

	const user = $derived(data.user);
	const isAdmin = $derived(user?.role === 'ADMIN');
	const currentPath = $derived(page.url.pathname);

	const sections = $derived([
		{ href: '/settings/profile', label: m.settings_profile(), show: true },
		{ href: '/settings/preferences', label: m.settings_preferences(), show: true },
		{ href: '/settings/security', label: m.settings_security(), show: true },
		{ href: '/settings/users', label: m.settings_users(), show: isAdmin }
	]);
</script>

<div class="mx-auto max-w-4xl py-2">
	<h1 class="mb-6 text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
		{m.settings_title()}
	</h1>

	<!-- Mobile: horizontal tabs -->
	<div
		class="mb-6 flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-800 md:hidden"
	>
		{#each sections as section (section.href)}
			{#if section.show}
				<a
					href={section.href}
					class="whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors {currentPath.startsWith(
						section.href
					)
						? 'border-gray-900 text-gray-900 dark:border-gray-100 dark:text-gray-100'
						: 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-300'}"
				>
					{section.label}
				</a>
			{/if}
		{/each}
	</div>

	<div class="flex gap-8">
		<!-- Desktop: sidebar -->
		<nav class="hidden w-48 shrink-0 md:block">
			<ul class="space-y-1">
				{#each sections as section (section.href)}
					{#if section.show}
						<li>
							<a
								href={section.href}
								class="block rounded-md px-3 py-2 text-sm font-medium transition-colors {currentPath.startsWith(
									section.href
								)
									? 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
									: 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100'}"
							>
								{section.label}
							</a>
						</li>
					{/if}
				{/each}
			</ul>
		</nav>

		<!-- Content area -->
		<div class="min-w-0 flex-1">
			{@render children()}
		</div>
	</div>
</div>
