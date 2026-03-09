<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'default' | 'success' | 'warning' | 'info';
		size?: 'sm' | 'md';
		class?: string;
		children: Snippet;
	}

	let { variant = 'default', size = 'sm', class: className = '', children }: Props = $props();

	const variantClasses: Record<string, string> = {
		default: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
		success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
		warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
		info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
	};

	const sizeClasses: Record<string, string> = {
		sm: 'px-2 py-0.5 text-xs',
		md: 'px-2.5 py-1 text-sm'
	};

	let classes = $derived(
		`inline-flex items-center rounded-full font-medium ${variantClasses[variant]} ${sizeClasses[size]} ${className}`.trim()
	);
</script>

<span class={classes}>
	{@render children()}
</span>
