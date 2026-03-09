<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	interface Props extends HTMLInputAttributes {
		label: string;
		error?: string;
	}

	let {
		label,
		name,
		type = 'text',
		error = '',
		placeholder = '',
		required = false,
		value = $bindable(''),
		class: className = '',
		...rest
	}: Props = $props();
</script>

<div class={className}>
	<label for={name} class="block text-sm font-medium text-gray-700 dark:text-gray-300">
		{label}
		{#if required}
			<span class="text-red-500">*</span>
		{/if}
	</label>
	<input
		{name}
		id={name}
		{type}
		{placeholder}
		{required}
		bind:value
		class="mt-1 block w-full rounded-md border px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-1 dark:text-gray-100 dark:placeholder-gray-500
		{error
			? 'border-red-500 focus:border-red-500 focus:ring-red-500 dark:border-red-500'
			: 'border-gray-300 focus:border-gray-900 focus:ring-gray-900 dark:border-gray-700 dark:focus:border-gray-100 dark:focus:ring-gray-100'}
		bg-white dark:bg-gray-800"
		{...rest}
	/>
	{#if error}
		<p class="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
	{/if}
</div>
