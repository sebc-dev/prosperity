<script lang="ts">
	interface Props {
		name: string;
		value?: string;
		label?: string;
		class?: string;
	}

	const PRESET_COLORS = [
		'#3B82F6', // blue
		'#10B981', // emerald
		'#F59E0B', // amber
		'#EF4444', // red
		'#8B5CF6', // violet
		'#EC4899', // pink
		'#06B6D4', // cyan
		'#F97316', // orange
		'#6366F1', // indigo
		'#84CC16' // lime
	];

	let {
		name,
		value = $bindable(PRESET_COLORS[0]),
		label = '',
		class: className = ''
	}: Props = $props();
</script>

<div class={className}>
	{#if label}
		<span class="block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
	{/if}
	<div class="mt-2 flex flex-wrap gap-2">
		{#each PRESET_COLORS as color (color)}
			<button
				type="button"
				onclick={() => (value = color)}
				class="flex h-8 w-8 items-center justify-center rounded-full border-2 transition-transform hover:scale-110 {value ===
				color
					? 'border-gray-900 dark:border-gray-100'
					: 'border-transparent'}"
				style="background-color: {color}"
				aria-label="Select color {color}"
			>
				{#if value === color}
					<svg
						class="h-4 w-4 text-white"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="3"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
				{/if}
			</button>
		{/each}
	</div>
	<input type="hidden" {name} {value} />
</div>
