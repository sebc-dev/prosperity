import { useCallback, useEffect, useState, type ReactNode } from 'react'

import { ThemeContext, THEME_STORAGE_KEY, type Theme } from '@/hooks/use-theme'

/** Thème initial : valeur stockée si valide, sinon préférence système. La même
 *  heuristique (clé + prefers-color-scheme) est dupliquée dans le script anti-FOUC
 *  d'index.html (D7) ; cohérence des deux à vérifier en Playwright (§6). */
function readInitial(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') {
    return stored
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readInitial)

  // Effet idempotent (StrictMode-safe) : pose/retire `.dark` sur <html> et
  // réécrit la même clé localStorage à chaque rendu du thème.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return <ThemeContext value={{ theme, toggle }}>{children}</ThemeContext>
}
