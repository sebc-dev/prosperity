<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		padding?: string;
		hover?: boolean;
		class?: string;
		children: Snippet;
	}

	let { padding = 'p-6', hover = false, class: className = '', children }: Props = $props();

	let classes = $derived(
		`rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 ${padding} ${hover ? 'transition-shadow hover:shadow-md dark:hover:shadow-gray-800/50' : ''} ${className}`.trim()
	);
</script>

<div class={classes}>
	{@render children()}
</div>
