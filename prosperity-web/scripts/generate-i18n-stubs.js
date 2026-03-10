#!/usr/bin/env node

/**
 * Generates i18n message function stubs for svelte-check compatibility.
 *
 * Paraglide-js v2 generates real message functions only through its Vite plugin
 * (virtual modules). Tools that run outside Vite (e.g. svelte-check) cannot see
 * them. This script reads the source language JSON and produces stub exports in
 * src/lib/i18n/messages/_index.js so that type checking passes.
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');

const SOURCE_JSON = join(projectRoot, 'messages', 'fr.json');
const OUT_DIR = join(projectRoot, 'src', 'lib', 'i18n', 'messages');
const OUT_FILE = join(OUT_DIR, '_index.js');
const OUT_DTS = join(OUT_DIR, '_index.d.ts');
const MESSAGES_DTS = join(projectRoot, 'src', 'lib', 'i18n', 'messages.d.ts');

const PARAM_PATTERN = /\{(\w+)\}/g;

let messages;
try {
	messages = JSON.parse(readFileSync(SOURCE_JSON, 'utf-8'));
} catch (err) {
	console.error(`Failed to read or parse source language JSON at: ${SOURCE_JSON}`);
	console.error(err.message);
	process.exit(1);
}

const lines = ['/* eslint-disable */'];
lines.push('/** @typedef {import("../runtime.js").LocalizedString} LocalizedString */');
lines.push('');

const dtsLines = [];
dtsLines.push('type LocalizedString = import("../runtime.js").LocalizedString;');
dtsLines.push('');

const VALID_IDENTIFIER = /^[a-zA-Z_$][a-zA-Z0-9_$]*$/;

for (const [key, value] of Object.entries(messages)) {
	if (!VALID_IDENTIFIER.test(key)) {
		console.warn(`Skipping invalid key "${key}": not a valid JS identifier`);
		continue;
	}

	const params = [];
	let match;
	while ((match = PARAM_PATTERN.exec(value)) !== null) {
		params.push(match[1]);
	}

	if (params.length > 0) {
		const paramsType = params.map((p) => `${p}: string`).join(', ');
		lines.push(
			`export const ${key} = (/** @type {{ ${paramsType} }} */ params) => /** @type {LocalizedString} */ ("stub");`
		);
		dtsLines.push(`export declare const ${key}: (params: { ${paramsType} }) => LocalizedString;`);
	} else {
		lines.push(`export const ${key} = () => /** @type {LocalizedString} */ ("stub");`);
		dtsLines.push(`export declare const ${key}: () => LocalizedString;`);
	}
}

lines.push('');

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(OUT_FILE, lines.join('\n'), 'utf-8');
writeFileSync(OUT_DTS, dtsLines.join('\n') + '\n', 'utf-8');

// Fix messages.d.ts: paraglide-js compile generates "export {}" which hides
// the re-exports from messages.js. Overwrite with proper re-exports.
writeFileSync(
	MESSAGES_DTS,
	"export * from './messages/_index.js';\nexport * as m from './messages/_index.js';\n",
	'utf-8'
);

console.log(`Generated ${Object.keys(messages).length} message stubs in ${OUT_FILE}`);
console.log(`Generated type declarations in ${OUT_DTS}`);
console.log(`Fixed re-exports in ${MESSAGES_DTS}`);
