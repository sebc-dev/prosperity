<script lang="ts">
	interface Option {
		value: string;
		label: string;
	}

	interface Props {
		label: string;
		name: string;
		options: Option[];
		value?: string;
		error?: string;
		required?: boolean;
		class?: string;
	}

	let {
		label,
		name,
		options,
		value = $bindable(''),
		error = '',
		required = false,
		class: className = ''
	}: Props = $props();
</script>

<div class={className}>
	<label for={name} class="block text-sm font-medium text-gray-700 dark:text-gray-300">
		{label}
		{#if required}
			<span class="text-red-500">*</span>
		{/if}
	</label>
	<select
		{name}
		id={name}
		{required}
		bind:value
		class="mt-1 block w-full appearance-none rounded-md border bg-white px-3 py-2 pr-8 text-sm text-gray-900 focus:outline-none focus:ring-1 dark:bg-gray-800 dark:text-gray-100
		{error
			? 'border-red-500 focus:border-red-500 focus:ring-red-500 dark:border-red-500'
			: 'border-gray-300 focus:border-gray-900 focus:ring-gray-900 dark:border-gray-700 dark:focus:border-gray-100 dark:focus:ring-gray-100'}"
	>
		{#each options as option}
			<option value={option.value}>{option.label}</option>
		{/each}
	</select>
	{#if error}
		<p class="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
	{/if}
</div>
