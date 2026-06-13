import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'

// StrictMode dès le bootstrap (D9) : révèle les double-exécutions d'effets de
// React 19 en dev, avant l'arrivée des hooks PowerSync (S14.4).
const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Élément racine #root introuvable dans index.html')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
