class PreferencesStore {
	theme = $state<'light' | 'dark' | 'system'>('system');
	locale = $state<'fr' | 'en'>('fr');
	defaultCurrency = $state('EUR');

	resolvedTheme = $derived<'light' | 'dark'>(
		this.theme === 'system'
			? typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
				? 'dark'
				: 'light'
			: this.theme
	);

	setTheme(theme: 'light' | 'dark' | 'system') {
		this.theme = theme;
		if (typeof document !== 'undefined') {
			document.documentElement.classList.toggle('dark', this.resolvedTheme === 'dark');
			document.cookie = `theme=${theme};path=/;max-age=${60 * 60 * 24 * 365};samesite=lax`;
		}
	}

	setLocale(locale: 'fr' | 'en') {
		this.locale = locale;
	}

	setDefaultCurrency(currency: string) {
		this.defaultCurrency = currency;
	}
}

export const preferences = new PreferencesStore();
