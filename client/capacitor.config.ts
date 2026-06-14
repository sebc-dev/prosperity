import type { CapacitorConfig } from '@capacitor/cli'

// Configuration Capacitor (S14.5). `webDir` = sortie Vite (`dist/`, S14.1). `androidScheme:'https'`
// évite le cleartext (capacitor-security NET001/NET003). Durcissements release (allowBackup,
// debug WebView) reportés en E16 ; signing release E16 ; iOS post-MVP (Android seul, CONTEXT.md).
const config: CapacitorConfig = {
  appId: 'dev.prosperity.app',
  appName: 'Prosperity',
  webDir: 'dist',
  server: { androidScheme: 'https' },
}

export default config
