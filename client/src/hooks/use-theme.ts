import { createContext, use } from 'react'

export type Theme = 'light' | 'dark'

export interface ThemeContextValue {
  theme: Theme
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

/** Clé localStorage du thème. Donnée NON sensible (énumération light|dark) →
 *  localStorage est sa place définitive, distincte du Secure Storage JWT (S14.5, D6). */
export const THEME_STORAGE_KEY = 'prosperity-theme'

export function useTheme(): ThemeContextValue {
  const ctx = use(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme doit être utilisé dans <ThemeProvider>')
  }
  return ctx
}
