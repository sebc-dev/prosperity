<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import * as m from '$lib/i18n/messages.js';
	import type { Snippet } from 'svelte';

	interface Props {
		data: {
			user: {
				id: string;
				email: string;
				displayName: string;
				role: string;
			};
		};
		children: Snippet;
	}

	let { data, children }: Props = $props();
	let mobileMenuOpen = $state(false);

	const navItems = [
		{
			href: '/',
			label: () => m.nav_dashboard(),
			icon: 'dashboard'
		},
		{
			href: '/accounts',
			label: () => m.accounts_title(),
			icon: 'accounts'
		},
		{
			href: '/settings',
			label: () => m.settings_title(),
			icon: 'settings'
		}
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

<div class="flex min-h-screen bg-gray-50 dark:bg-gray-950">
	<!-- Desktop Sidebar -->
	<aside
		class="hidden w-64 flex-shrink-0 border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 lg:flex lg:flex-col"
	>
		<!-- Logo -->
		<div class="flex h-16 items-center border-b border-gray-200 px-6 dark:border-gray-800">
			<h1 class="text-lg font-semibold tracking-tight text-gray-900 dark:text-gray-100">
				Prosperity
			</h1>
		</div>

		<!-- Navigation -->
		<nav class="flex-1 space-y-1 px-3 py-4">
			{#each navItems as item}
				<a
					href={item.href}
					class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors
					{isActive(item.href)
						? 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
						: 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-100'}"
				>
					{#if item.icon === 'dashboard'}
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
						</svg>
					{:else if item.icon === 'accounts'}
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" />
						</svg>
					{:else if item.icon === 'settings'}
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
							<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
						</svg>
					{/if}
					{item.label()}
				</a>
			{/each}
		</nav>

		<!-- User section -->
		<div class="border-t border-gray-200 p-4 dark:border-gray-800">
			<div class="flex items-center gap-3">
				<div
					class="flex h-8 w-8 items-center justify-center rounded-full bg-gray-200 text-sm font-medium text-gray-700 dark:bg-gray-700 dark:text-gray-300"
				>
					{data.user.displayName?.charAt(0).toUpperCase() ?? '?'}
				</div>
				<div class="flex-1 truncate">
					<p class="text-sm font-medium text-gray-900 dark:text-gray-100">
						{data.user.displayName}
					</p>
					<p class="truncate text-xs text-gray-500 dark:text-gray-400">{data.user.email}</p>
				</div>
				<form method="POST" action="/logout" use:enhance>
					<button
						type="submit"
						class="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
						title={m.nav_logout()}
					>
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
						</svg>
					</button>
				</form>
			</div>
		</div>
	</aside>

	<!-- Mobile Header -->
	<div class="flex flex-1 flex-col lg:min-w-0">
		<header class="flex h-16 items-center gap-4 border-b border-gray-200 bg-white px-4 dark:border-gray-800 dark:bg-gray-900 lg:hidden">
			<button
				type="button"
				onclick={() => (mobileMenuOpen = !mobileMenuOpen)}
				class="rounded-md p-2 text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
			>
				<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					{#if mobileMenuOpen}
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					{:else}
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
					{/if}
				</svg>
			</button>
			<h1 class="text-lg font-semibold tracking-tight text-gray-900 dark:text-gray-100">
				Prosperity
			</h1>
		</header>

		<!-- Mobile Navigation Drawer -->
		{#if mobileMenuOpen}
			<div class="border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-800 dark:bg-gray-900 lg:hidden">
				<nav class="space-y-1">
					{#each navItems as item}
						<a
							href={item.href}
							onclick={() => (mobileMenuOpen = false)}
							class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors
							{isActive(item.href)
								? 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
								: 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-100'}"
						>
							{item.label()}
						</a>
					{/each}
				</nav>
				<div class="mt-2 border-t border-gray-200 pt-2 dark:border-gray-800">
					<form method="POST" action="/logout" use:enhance>
						<button
							type="submit"
							class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/50 dark:hover:text-gray-100"
						>
							{m.nav_logout()}
						</button>
					</form>
				</div>
			</div>
		{/if}

		<!-- Main Content -->
		<main class="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
			<div class="mx-auto max-w-6xl">
				{@render children()}
			</div>
		</main>
	</div>
</div>
