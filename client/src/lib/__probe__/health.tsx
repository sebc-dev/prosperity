import { useEffect, useState } from 'react'

/**
 * Sonde de bootstrap : démontre l'interception réseau MSW (§5.2). Jetable — à retirer
 * quand un vrai appel typé arrive (S14.6). Sous `__probe__/`, hors `coverage.include`.
 */
export function HealthProbe() {
  const [status, setStatus] = useState('…')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        // URL résolue contre l'origine (relatif → absolu) : indispensable sous le
        // `fetch` Node de jsdom, et réaliste (le navigateur résout pareil).
        const res = await fetch(new URL('/api/health', window.location.origin))
        const data = (await res.json()) as { status: string }
        if (active) setStatus(data.status)
      } catch {
        if (active) setStatus('erreur')
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  return <p>statut : {status}</p>
}
