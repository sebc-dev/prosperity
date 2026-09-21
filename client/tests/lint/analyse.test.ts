import { readFileSync } from 'node:fs'
import path from 'node:path'

import { ESLint } from 'eslint'
import { describe, expect, test } from 'vitest'

// Preuve de comportement de la passe `npm run analyse` (ticket 01), un test par critère
// (SC-01<lettre> dans le nom). Patron du design.md : `new ESLint({ cwd, overrideConfigFile })`
// puis `lintText(source, { filePath })` sur le chemin d'un fichier RÉEL de `src/` — le contenu
// analysé est la chaîne passée à `lintText`, jamais le contenu réel sur disque. `projectService`
// n'exige donc pas que le fichier existe : il suffit qu'il soit sous un chemin couvert par
// `tsconfig.json` (`include: ["src", "tests", …]`). Aucune fixture n'est écrite sur disque —
// elle entrerait elle-même dans le périmètre linté par `analyse`.

const clientRoot = path.resolve(import.meta.dirname, '../..')
const configPath = path.join(clientRoot, 'eslint.config.analyse.js')
const anchorFile = path.join(clientRoot, 'src/lib/format.ts')
const anchorTestFile = path.join(clientRoot, 'src/lib/format.test.ts')
const routeTreeFile = path.join(clientRoot, 'src/routeTree.gen.ts')
const schemaFile = path.join(clientRoot, 'src/lib/api/schema.d.ts')

// Une seule instance ESLint partagée par tous les tests de ce fichier : `projectService`
// construit un programme TypeScript à la première utilisation (coût dominant, largement
// > 5s sous charge CI concurrente) puis le réutilise pour les appels suivants. Instancier une
// fois évite de repayer ce coût à chaque test (FIRST — rapide) sans coupler les tests entre eux :
// chaque test fournit sa propre source et son propre `filePath` à `lintText`, aucun état mutable
// n'est partagé au-delà du cache de programme TS.
const analyseEslint = new ESLint({ cwd: clientRoot, overrideConfigFile: configPath })

// Le premier appel réel (construction du programme TypeScript par `projectService`) dépasse le
// timeout par défaut de vitest (5s) sous charge CI concurrente ; 20s couvre cette construction
// initiale pour l'ensemble des tests de ce fichier.
const ESLINT_TEST_TIMEOUT = 20_000

describe('npm run analyse — config eslint.config.analyse.js', () => {
  test(
    'SC-01a — une fonction de complexité cognitive > 15 dans src/ fait échouer analyse, en citant fichier, ligne, règle et valeur mesurée',
    async () => {
      // Arrange : une fonction dont les branches (if imbriqués, boucles, switch, try/catch,
      // opérateurs logiques) dépassent largement le seuil de 15 fixé dans la config.
      const source = `
export function tooComplex(a: number, b: number, c: number, d: number, e: number): number {
  let result = 0
  if (a > 0) {
    if (b > 0) {
      if (c > 0) {
        if (d > 0) {
          if (e > 0) { result += 1 } else { result += 2 }
        } else { result += 3 }
      } else { result += 4 }
    } else { result += 5 }
  } else { result += 6 }
  for (let i = 0; i < a; i++) {
    if (i % 2 === 0) { result += i } else { result -= i }
  }
  while (b > 0) {
    if (b % 3 === 0) { result += b } else { result -= b }
    b--
  }
  switch (c) {
    case 1: result += 1; break
    case 2: result += 2; break
    case 3: result += 3; break
    default: result += 0
  }
  try {
    if (d > 100) { throw new Error('too big') }
  } catch (err) {
    result += 1
  }
  return result && e ? result : e
}
`
      // Act
      const [result] = await analyseEslint.lintText(source, { filePath: anchorFile })
      expect(result).toBeDefined()
      if (!result) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)

      // Assert : la remontée cite le fichier (filePath du résultat), la ligne de la fonction,
      // la règle sonarjs/cognitive-complexity, et la valeur mesurée dans le message.
      const complexityMessages = result.messages.filter(
        (m) => m.ruleId === 'sonarjs/cognitive-complexity',
      )
      expect(complexityMessages).toHaveLength(1)
      const [message] = complexityMessages
      expect(message).toBeDefined()
      if (!message) throw new Error('aucune remontée sonarjs/cognitive-complexity')
      expect(result.filePath).toBe(anchorFile)
      expect(message.line).toBeGreaterThan(0)
      // « Refactor this function to reduce its Cognitive Complexity from <mesurée> to the 15
      // allowed. » — les deux nombres (mesurée, seuil) sont dans le texte de la remontée.
      expect(message.message).toMatch(/Cognitive Complexity from \d+ to the 15 allowed/)
      expect(result.errorCount).toBeGreaterThan(0)
    },
    ESLINT_TEST_TIMEOUT,
  )

  test(
    'SC-01b — un appel non intercepté d’une fonction async dans src/ fait échouer analyse sur @typescript-eslint/no-floating-promises',
    async () => {
      // Arrange : `fetchThing()` rend une Promise, appelée sans await/void/.then/.catch.
      const source = `
async function fetchThing(): Promise<number> {
  return 42
}

export function callIt(): void {
  fetchThing()
}
`
      // Act
      const [result] = await analyseEslint.lintText(source, { filePath: anchorFile })
      expect(result).toBeDefined()
      if (!result) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)

      // Assert
      const floatingMessages = result.messages.filter(
        (m) => m.ruleId === '@typescript-eslint/no-floating-promises',
      )
      expect(floatingMessages).toHaveLength(1)
      expect(floatingMessages[0]).toBeDefined()
      if (!floatingMessages[0])
        throw new Error('aucune remontée @typescript-eslint/no-floating-promises')
      expect(floatingMessages[0].line).toBe(7)
    },
    ESLINT_TEST_TIMEOUT,
  )

  test(
    'SC-01c — deux fonctions au corps identique dans un même fichier de src/ font échouer analyse sur sonarjs/no-identical-functions',
    async () => {
      // Arrange : `alpha` et `beta` ont exactement le même corps.
      const source = `
export function alpha(x: number): number {
  const y = x + 1
  const z = y * 2
  return z - 1
}

export function beta(x: number): number {
  const y = x + 1
  const z = y * 2
  return z - 1
}
`
      // Act
      const [result] = await analyseEslint.lintText(source, { filePath: anchorFile })
      expect(result).toBeDefined()
      if (!result) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)

      // Assert
      const identicalMessages = result.messages.filter(
        (m) => m.ruleId === 'sonarjs/no-identical-functions',
      )
      expect(identicalMessages).toHaveLength(1)
    },
    ESLINT_TEST_TIMEOUT,
  )

  test(
    'SC-01d — une infraction dans src/routeTree.gen.ts ou src/lib/api/schema.d.ts n’est pas remontée par analyse (fichiers hors périmètre)',
    async () => {
      // Arrange : la même source qu'en SC-01b, qui remonte @typescript-eslint/no-floating-promises
      // quand elle est attribuée à un fichier DANS le périmètre.
      const source = `
async function fetchThing(): Promise<number> {
  return 42
}

export function callIt(): void {
  fetchThing()
}
`

      // Act + Assert : les deux artefacts générés sont explicitement ignorés par la config …
      expect(await analyseEslint.isPathIgnored(routeTreeFile)).toBe(true)
      expect(await analyseEslint.isPathIgnored(schemaFile)).toBe(true)

      // … et la même source, une fois attribuée à ces chemins, ne produit AUCUNE remontée de
      // règle (seul un avertissement « fichier ignoré », sans ruleId, peut apparaître).
      const [routeTreeResult] = await analyseEslint.lintText(source, { filePath: routeTreeFile })
      expect(routeTreeResult).toBeDefined()
      if (!routeTreeResult)
        throw new Error('lintText n’a rendu aucun résultat pour ' + routeTreeFile)
      const [schemaResult] = await analyseEslint.lintText(source, { filePath: schemaFile })
      expect(schemaResult).toBeDefined()
      if (!schemaResult) throw new Error('lintText n’a rendu aucun résultat pour ' + schemaFile)
      expect(routeTreeResult.messages.filter((m) => m.ruleId !== null)).toHaveLength(0)
      expect(schemaResult.messages.filter((m) => m.ruleId !== null)).toHaveLength(0)
    },
    ESLINT_TEST_TIMEOUT,
  )

  test(
    'SC-01e — quand aucun fichier de src/ n’enfreint une règle de la passe, analyse sort en succès (code 0) sans remontée',
    async () => {
      // Arrange : une fonction simple, sans complexité, sans promesse flottante, sans duplication.
      const source = `
export function addOne(x: number): number {
  return x + 1
}
`
      // Act
      const [result] = await analyseEslint.lintText(source, { filePath: anchorFile })
      expect(result).toBeDefined()
      if (!result) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)

      // Assert : aucun message, donc aucune remontée — l'équivalent du code de sortie 0 pour ce
      // fichier (ESLint sort en 1 dès qu'un `errorCount` est non nul sur au moins un fichier).
      expect(result.messages).toHaveLength(0)
      expect(result.errorCount).toBe(0)
      expect(result.warningCount).toBe(0)
    },
    ESLINT_TEST_TIMEOUT,
  )

  test('SC-01f — toute règle désactivée ou assouplie pour les fichiers de test porte, sur sa ligne, un commentaire avec le nombre de remontées éteintes et la raison', () => {
    // Arrange : le texte source de la config elle-même — ce critère porte sur la convention
    // d'écriture (commentaire de justification), pas sur un comportement d'exécution.
    const configSource = readFileSync(configPath, 'utf-8')
    const lines = configSource.split('\n')

    // Un bloc `files: [...]` scopé aux fichiers de test (glob contenant `.test.` ou `tests/`)
    // suivi d'un bloc `rules: { … }` : on y cherche toute entrée assouplie ('off' ou 'warn').
    const testFilesBlockStarts: number[] = []
    lines.forEach((line, i) => {
      if (/files:\s*\[[^\]]*(\.test\.|tests\/)[^\]]*\]/.test(line)) {
        testFilesBlockStarts.push(i)
      }
    })
    expect(testFilesBlockStarts.length).toBeGreaterThan(0)

    // Toute ligne `'<rule>': 'off',` ou `'<rule>': 'warn',` trouvée après un tel `files:` et
    // avant la fermeture du bloc `rules: { … }` (accolade fermante seule sur sa ligne) est une
    // règle assouplie pour les tests, et doit avoir un commentaire attaché juste au-dessus.
    const relaxedRuleLineRegex = /^\s*['"][^'"]+['"]:\s*['"](?:off|warn)['"],?\s*$/
    const rulesBlockEndRegex = /^\s*},?\s*$/

    const relaxedRuleLines: number[] = []
    for (const startIdx of testFilesBlockStarts) {
      for (let i = startIdx + 1; i < lines.length; i++) {
        const line = lines[i]
        const previous = lines[i - 1]
        if (line === undefined || previous === undefined) {
          throw new Error(`ligne ${i} hors de la config lue (${lines.length} lignes)`)
        }
        if (rulesBlockEndRegex.test(line) && !relaxedRuleLineRegex.test(previous)) {
          // Fin plausible du bloc `rules: { … }` (accolade seule, précédée d'une ligne qui
          // n'est pas elle-même une règle assouplie) : on arrête de scanner ce bloc-là.
          break
        }
        if (relaxedRuleLineRegex.test(line)) {
          relaxedRuleLines.push(i)
        }
      }
    }

    // Au moins une règle assouplie pour les tests existe dans la config (sinon ce critère
    // n'a rien à vérifier — mais la config du ticket en porte au moins deux).
    expect(relaxedRuleLines.length).toBeGreaterThan(0)

    for (const ruleLineIdx of relaxedRuleLines) {
      // Remonte les lignes de commentaire contiguës juste au-dessus de la règle assouplie.
      const commentLines: string[] = []
      let cursor = ruleLineIdx - 1
      let candidate = lines[cursor]
      while (cursor >= 0 && candidate !== undefined && /^\s*\/\//.test(candidate)) {
        commentLines.unshift(candidate)
        cursor--
        candidate = lines[cursor]
      }
      const commentText = commentLines.join(' ')

      // Un commentaire est présent…
      expect(commentText.length).toBeGreaterThan(0)
      // … porte le nombre de remontées éteintes (un compte chiffré)…
      expect(commentText).toMatch(/\d+\s+remont/i)
      // … et une raison au-delà du seul chiffre (texte substantiel, pas juste "3 remontées").
      expect(commentText.replace(/\d+\s+remont[ée]es?/gi, '').trim().length).toBeGreaterThan(20)
    }
  })

  test(
    'SC-01g — la même règle assouplie pour les tests reste remontée dans src/ hors tests (le calibrage ne touche jamais la production)',
    async () => {
      // Arrange : une fonction vide, ciblée par @typescript-eslint/no-empty-function (assoupli en
      // 'off' pour les fichiers de test dans la config).
      const emptyFunctionSource = `
export function noop(): void {}
`
      // Act + Assert : remontée dans un fichier de src/ hors tests…
      const [srcResult] = await analyseEslint.lintText(emptyFunctionSource, {
        filePath: anchorFile,
      })
      expect(srcResult).toBeDefined()
      if (!srcResult) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)
      expect(
        srcResult.messages.filter((m) => m.ruleId === '@typescript-eslint/no-empty-function'),
      ).toHaveLength(1)

      // … mais éteinte dans un fichier de test co-localisé (même contenu, chemin `*.test.ts`).
      const [testResult] = await analyseEslint.lintText(emptyFunctionSource, {
        filePath: anchorTestFile,
      })
      expect(testResult).toBeDefined()
      if (!testResult) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorTestFile)
      expect(
        testResult.messages.filter((m) => m.ruleId === '@typescript-eslint/no-empty-function'),
      ).toHaveLength(0)

      // Même démonstration avec sonarjs/no-duplicate-string (seuil 5, assoupli en 'off' pour les
      // tests) : 5 occurrences du même littéral suffisent à déclencher la règle en src/.
      const duplicateStringSource = `
export function dupStrings(): string[] {
  return ['same-value', 'same-value', 'same-value', 'same-value', 'same-value']
}
`
      const [srcDupResult] = await analyseEslint.lintText(duplicateStringSource, {
        filePath: anchorFile,
      })
      expect(srcDupResult).toBeDefined()
      if (!srcDupResult) throw new Error('lintText n’a rendu aucun résultat pour ' + anchorFile)
      expect(
        srcDupResult.messages.filter((m) => m.ruleId === 'sonarjs/no-duplicate-string'),
      ).toHaveLength(1)

      const [testDupResult] = await analyseEslint.lintText(duplicateStringSource, {
        filePath: anchorTestFile,
      })
      expect(testDupResult).toBeDefined()
      if (!testDupResult)
        throw new Error('lintText n’a rendu aucun résultat pour ' + anchorTestFile)
      expect(
        testDupResult.messages.filter((m) => m.ruleId === 'sonarjs/no-duplicate-string'),
      ).toHaveLength(0)
    },
    ESLINT_TEST_TIMEOUT,
  )
})
