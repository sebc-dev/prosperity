# Runbook — Build & run Android (Capacitor)

> Story S14.5 (E14 Frontend bootstrap). L'app web (`client/`, Vite → `dist/`) est emballée dans
> **Capacitor 8** ; cible **Android seul** en MVP (pas d'iOS — `CONTEXT.md`). Le projet natif
> `client/android/` est committé. La validation sur émulateur est **manuelle** (pas de SDK Android
> en CI ; cf. `docs/Stratégie de tests.md §6.1` « pas de tests sur app Capacitor compilée »).

## 1. Prérequis (poste local)

- **Android Studio** (récent) + **Android SDK** (Platform + Build-Tools) via le SDK Manager.
- **JDK 21** — baseline Capacitor 8. Vérifier les versions exactes Gradle/SDK exigées par Cap 8
  à jour (cf. skill `capacitor-app-upgrade-v7-to-v8`) si le build Gradle échoue.
- Un **AVD** (Android Virtual Device) configuré dans Android Studio (émulateur).
- **Node ≥ 22** (déjà requis par `client/`).
- `android/local.properties` (chemin du SDK) est **généré localement et gitignoré** — ne pas le
  committer.

## 2. Boucle de build

Depuis `client/` :

```bash
npm run build              # tsc --noEmit && vite build → dist/ (bundle PRODUCTION)
npx cap sync android       # copie dist/ dans le projet natif + enregistre les plugins
npx cap run android        # build Gradle + déploie sur l'émulateur ; l'app doit charger
```

> **Toujours `npx cap sync android` après chaque `npm run build`** (la WebView sert une copie
> figée de `dist/`, pas le serveur de dev). `npx cap open android` ouvre le projet dans Android
> Studio si besoin de débogage natif.

## 3. Signing

- **V1 = debug only** : Android signe automatiquement avec la clé debug locale (suffisant pour
  l'émulateur). Aucune action.
- **Release signing** (keystore, Play Store) → **reporté en E16** (déploiement).
- **Ne jamais committer de keystore release** (`*.jks` / `*.keystore`).

## 4. Durcissements release — à ne pas oublier (E16)

Non requis pour le V1 debug-only émulateur, **prérequis du signing release E16** (éditer le
`AndroidManifest.xml` committé) :

- `android:allowBackup="false"` (capacitor-security **AND004** — sinon le backup Android peut
  exfiltrer les données de l'app).
- `webContentsDebuggingEnabled=false` en release (**CAP001**).
- Revue complète du `AndroidManifest.xml` (permissions, exported components).

## 5. Stockage sécurisé du JWT (Secure Storage)

- `lib/storage/` route le **Secure Storage natif** (Keystore Android / Keychain) sur mobile vs
  `localStorage` sur web. Plugin : `@aparajita/capacitor-secure-storage` — **Cap-8-ready, en
  place** (chemin nominal) → **STO006 résolu sur natif** (le JWT ne vit plus en localStorage sur
  mobile). La contingence *stub fail-closed* (opt-in `VITE_ALLOW_INSECURE_STORAGE`) **n'a pas eu
  lieu d'être** ; si le plugin régressait et qu'un stub était réintroduit, l'attendu « STO006
  résolu sur natif » deviendrait conditionnel au retour du plugin réel.
- **Résiduel web (inhérent)** : sur navigateur, pas de Keystore → le JWT reste en `localStorage`
  (exposition XSS). Vraie mitigation = transport auth alternatif (cookie httpOnly), **hors-MVP**.
- **Consommation du JWT** (login, `getToken` async via `storage`, refresh-401) = **S14.6**. Le
  wrapper est provisionné ici, pas encore branché (`auth-token.ts` inchangé, D5).

## 6. Limites V1

- **Android seul** (pas d'iOS — `CONTEXT.md`).
- **Pas de validation émulateur en CI** : la boucle §2 est manuelle. La CI ne couvre que le
  web (`npm run build` + `lint` + `test`, dont `tests/capacitor.config.test.ts` qui verrouille
  `appId`/`webDir`/`androidScheme` sans SDK).

## 7. Audit sécurité (optionnel, local)

```bash
npx capsec scan --severity high   # skill capacitor-security
```

Attendus : **STO002** résiduel **web uniquement** (localStorage, cf. §5) ; **STO006** résolu sur
natif (plugin réel) ; `androidScheme: 'https'` ferme **NET001/NET003** (pas de cleartext).
