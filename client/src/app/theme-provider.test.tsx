import { render } from '@testing-library/react'
import { expect, test } from 'vitest'

import { ThemeProvider } from '@/app/theme-provider'
import { THEME_STORAGE_KEY } from '@/hooks/use-theme'

const html = () => document.documentElement

// Branche 1 de readInitial : valeur stockée valide.
test('init depuis localStorage : "dark" → <html> reçoit .dark', () => {
  localStorage.setItem(THEME_STORAGE_KEY, 'dark')
  render(<ThemeProvider>contenu</ThemeProvider>)
  expect(html().classList.contains('dark')).toBe(true)
})

// Branche 2 (fallback) : storage vide → sombre par défaut (décision #240).
test('fallback : storage vide → .dark par défaut', () => {
  render(<ThemeProvider>contenu</ThemeProvider>)
  expect(html().classList.contains('dark')).toBe(true)
})
