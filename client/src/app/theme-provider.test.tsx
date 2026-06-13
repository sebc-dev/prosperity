import { render } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { ThemeProvider } from '@/app/theme-provider'
import { THEME_STORAGE_KEY } from '@/hooks/use-theme'

const html = () => document.documentElement

// Branche 1 de readInitial : valeur stockée valide.
test('init depuis localStorage : "dark" → <html> reçoit .dark', () => {
  localStorage.setItem(THEME_STORAGE_KEY, 'dark')
  render(<ThemeProvider>contenu</ThemeProvider>)
  expect(html().classList.contains('dark')).toBe(true)
})

// Branche 2 (fallback) : storage vide → préférence système. Sans surcharge, le
// stub matchMedia par défaut (matches:false) ne couvrirait jamais cette branche.
test('fallback matchMedia : storage vide + prefers-color-scheme dark → .dark', () => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })

  render(<ThemeProvider>contenu</ThemeProvider>)
  expect(html().classList.contains('dark')).toBe(true)
})
