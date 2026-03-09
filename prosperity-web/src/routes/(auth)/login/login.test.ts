import { describe, it, expect, vi } from 'vitest';

// Mock Paraglide i18n messages before importing component
vi.mock('$lib/i18n/messages.js', () => ({
	login_title: () => 'Sign In',
	login_email: () => 'Email address',
	login_password: () => 'Password',
	login_submit: () => 'Sign in',
	login_error_invalid: () => 'Invalid email or password',
	session_expired: () => 'Session expired, please sign in again',
	common_loading: () => 'Loading...',
	common_error: () => 'An error occurred'
}));

import { render, screen } from '@testing-library/svelte';
import LoginPage from './+page.svelte';

describe('Login page', () => {
	it('renders email and password inputs', () => {
		render(LoginPage, { props: { form: null } });

		const emailInput = screen.getByLabelText('Email address');
		expect(emailInput).toBeDefined();
		expect(emailInput.getAttribute('type')).toBe('email');

		const passwordInput = screen.getByLabelText('Password');
		expect(passwordInput).toBeDefined();
		expect(passwordInput.getAttribute('type')).toBe('password');
	});

	it('renders submit button with correct label', () => {
		render(LoginPage, { props: { form: null } });

		const button = screen.getByRole('button', { name: 'Sign in' });
		expect(button).toBeDefined();
	});

	it('displays error message when form has error', () => {
		render(LoginPage, {
			props: { form: { error: 'invalid_credentials', email: 'test@test.com' } }
		});

		const errorMessage = screen.getByText('Invalid email or password');
		expect(errorMessage).toBeDefined();
	});

	it('renders the app name heading', () => {
		render(LoginPage, { props: { form: null } });

		const heading = screen.getByRole('heading', { name: 'Prosperity' });
		expect(heading).toBeDefined();
	});
});
