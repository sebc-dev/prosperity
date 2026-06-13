import { render } from '@testing-library/react'
import { expect, test } from 'vitest'

import { ThemeProvider } from '@/app/theme-provider'
import { THEME_STORAGE_KEY } from '@/hooks/use-theme'
import { stubMatchMedia } from '@tests/setup'

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
  stubMatchMedia(true) // surcharge `matches:true` ; restaurée par l'afterEach du setup

  render(<ThemeProvider>contenu</ThemeProvider>)
  expect(html().classList.contains('dark')).toBe(true)
})
