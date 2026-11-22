import { spawn } from 'node:child_process';
import { chmod, mkdir, mkdtemp, readFile, rm, stat, symlink, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import type { IncomingHttpHeaders, Server } from 'node:http';
import { tmpdir, userInfo } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  cleanupScript,
  isSafeRemoteDir,
  parsePreflight,
  pollScript,
  prepareScript,
  preflightScript,
  scannerScript,
  tarArgs,
  uploadCommand,
  versionScript,
} from './remote-kit.ts';
import type { RemoteConfig } from './remote-kit.ts';

const JETON = 'jeton-factice-0123';
const IMAGE = `docker.io/sonarsource/sonar-scanner-cli:12.1@sha256:${'ab'.repeat(32)}`;
const CFG: RemoteConfig = {
  sshHost: 'hote',
  envFile: '.config/prosperity-sonar/env',
  engine: 'docker',
  coverage: 'full',
};

let scratch = '';
let bin = '';
let home = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'sonar-remote-test-'));
  bin = join(scratch, 'bin');
  home = join(scratch, 'home');
  await mkdir(bin);
  await mkdir(join(home, '.config', 'prosperity-sonar'), { recursive: true });
  for (const tool of [
    'sed',
    'grep',
    'stat',
    'id',
    'head',
    'tr',
    'cat',
    'mktemp',
    'rm',
    'curl',
    'tar',
  ]) {
    await symlink(await locate(tool), join(bin, tool));
  }
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

async function locate(tool: string): Promise<string> {
  for (const dir of ['/usr/bin', '/bin']) {
    const path = join(dir, tool);
    if (
      await stat(path).then(
        () => true,
        () => false,
      )
    ) {
      return path;
    }
  }
  throw new Error(`outil introuvable : ${tool}`);
}

interface Ran {
  code: number;
  stdout: string;
}

/** Joue un script sur `sh -s` avec un PATH réduit au dossier `bin` du test (aucun vrai moteur de conteneur). */
function runScript(script: string, extra: Record<string, string> = {}): Promise<Ran> {
  return new Promise((resolve) => {
    const child = spawn('/bin/sh', ['-s'], {
      env: { PATH: bin, HOME: home, ...extra },
      stdio: ['pipe', 'pipe', 'ignore'],
    });
    const out: Buffer[] = [];
    child.stdout.on('data', (chunk: Buffer) => out.push(chunk));
    child.on('close', (code) => {
      resolve({ code: code ?? 1, stdout: Buffer.concat(out).toString('utf8') });
    });
    child.stdin.end(script);
  });
}

async function fakeEngine(name: string, infoExit: number, runExit = 0): Promise<string> {
  const log = join(scratch, 'engine.log');
  const body = `#!/bin/sh\nif [ "$1" = info ]; then exit ${String(infoExit)}; fi\nprintf '%s\\n' "$@" > '${log}'\nexit ${String(runExit)}\n`;
  await writeFile(join(bin, name), body);
  await chmod(join(bin, name), 0o755);
  return log;
}

async function envFile(content: string, mode = 0o600): Promise<string> {
  const path = join(home, '.config', 'prosperity-sonar', 'env');
  await writeFile(path, content);
  await chmod(path, mode);
  return path;
}

const GOOD = `SONAR_HOST_URL=http://localhost:9000\nSONAR_TOKEN=abcDEF123\n`;

describe('preflightScript (exécuté pour de vrai sur un faux dossier personnel)', () => {
  it('rend « ok » avec l’identité et le chemin absolu quand tout est en ordre', async () => {
    const path = await envFile(GOOD);
    await fakeEngine('docker', 0);
    const ran = await runScript(preflightScript(CFG));
    expect(ran.code).toBe(0);
    expect(parsePreflight(ran.stdout)).toStrictEqual({
      uid: userInfo().uid,
      gid: userInfo().gid,
      envFile: path,
    });
  });

  it.each([
    ['https://sonar.example', true],
    ['http://127.0.0.1:9000', true],
    ['http://localhost', true],
    ['http://sonar.example', false],
    ['http://localhost.evil.example', false],
    ['ftp://localhost', false],
  ])('adresse %s : acceptée %s', async (url, accepted) => {
    await envFile(`SONAR_HOST_URL=${url}\nSONAR_TOKEN=abcDEF123\n`);
    await fakeEngine('docker', 0);
    const ran = await runScript(preflightScript(CFG));
    expect(ran.stdout.startsWith('ok ')).toBe(accepted);
    expect(accepted || ran.stdout.trim() === 'host-url-refused').toBe(true);
  });

  it('refuse un fichier absent, lisible par d’autres, sans clé ou avec des guillemets', async () => {
    await fakeEngine('docker', 0);
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('env-file-missing');
    await envFile(GOOD, 0o644);
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('env-file-mode');
    await envFile('SONAR_HOST_URL=http://localhost:9000\n');
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('env-file-keys');
    await envFile(`SONAR_HOST_URL=http://localhost:9000\nSONAR_TOKEN="abc"\n`);
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('env-file-format');
  });

  it('refuse un moteur absent ou dont le démon n’est pas accessible à l’utilisateur', async () => {
    await envFile(GOOD);
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('engine-missing');
    await fakeEngine('docker', 1);
    expect((await runScript(preflightScript(CFG))).stdout.trim()).toBe('engine-access');
  });

  it('ne lit pas le jeton : le script ne contient aucune valeur de fichier', async () => {
    await envFile(GOOD);
    expect(preflightScript(CFG)).not.toContain('abcDEF123');
  });
});

describe('scannerScript', () => {
  const params = {
    image: IMAGE,
    dir: '/data/prosperity-sonar.AbC123',
    uid: 1000,
    gid: 1001,
    envFile: '/h/env',
  };

  it('lance le scanner avec le fichier d’environnement, sans jamais passer le jeton en argument', async () => {
    const log = await fakeEngine('docker', 0);
    const ran = await runScript(scannerScript(CFG, params));
    expect(ran.code).toBe(0);
    expect((await readFile(log, 'utf8')).trim().split('\n')).toStrictEqual([
      'run',
      '--rm',
      '--network',
      'host',
      '--user',
      '1000:1001',
      '--env-file',
      '/h/env',
      '-e',
      'SONAR_USER_HOME=/usr/src/reports/sonar/cache',
      '-v',
      '/data/prosperity-sonar.AbC123:/usr/src',
      IMAGE,
      '-Dsonar.analysis.coverage=full',
      '-Dsonar.scm.disabled=true',
    ]);
  });

  it('propage le code de sortie du moteur', async () => {
    await fakeEngine('docker', 0, 3);
    expect((await runScript(scannerScript(CFG, params))).code).toBe(3);
  });

  it('utilise --userns=keep-id pour Podman', async () => {
    const log = await fakeEngine('podman', 0);
    await runScript(scannerScript({ ...CFG, engine: 'podman' }, params));
    expect(await readFile(log, 'utf8')).toContain('--userns=keep-id');
  });

  it('refuse un dossier distant qui n’est pas celui d’un mktemp attendu', () => {
    expect(() => scannerScript(CFG, { ...params, dir: '/' })).toThrow('dossier distant');
  });
});

describe('scripts de lecture du serveur (jeton lu sur la machine distante, jamais en argument)', () => {
  let server: Server;
  let seen: IncomingHttpHeaders = {};
  let url = '';

  beforeEach(async () => {
    seen = {};
    server = createServer((req, res) => {
      seen = req.headers;
      const ok = req.headers.authorization === `Bearer ${JETON}`;
      if (req.url === '/api/server/version') {
        res.end('26.10.0');
      } else if (req.url === '/api/ce/task?id=AZ-12' && ok) {
        res.end('{"task":{"status":"SUCCESS"}}');
      } else {
        res.statusCode = 401;
        res.end('{}');
      }
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    url = `http://127.0.0.1:${String(typeof address === 'object' && address !== null ? address.port : 0)}`;
  });

  afterEach(async () => {
    await new Promise((resolve) => server.close(resolve));
  });

  it('pollScript interroge la tâche avec l’en-tête Bearer lu dans le fichier', async () => {
    const path = await envFile(`SONAR_HOST_URL=${url}/\nSONAR_TOKEN=${JETON}\n`);
    const script = pollScript({ envFile: path, taskId: 'AZ-12' });
    const ran = await runScript(script);
    expect(ran.code).toBe(0);
    expect(JSON.parse(ran.stdout)).toStrictEqual({ task: { status: 'SUCCESS' } });
    expect(seen.authorization).toBe(`Bearer ${JETON}`);
    expect(script).not.toContain(JETON);
  });

  it('pollScript échoue quand le serveur refuse le jeton', async () => {
    const path = await envFile(`SONAR_HOST_URL=${url}\nSONAR_TOKEN=autre\n`);
    expect((await runScript(pollScript({ envFile: path, taskId: 'AZ-12' }))).code).not.toBe(0);
  });

  it('versionScript lit la version du serveur', async () => {
    const path = await envFile(`SONAR_HOST_URL=${url}\nSONAR_TOKEN=${JETON}\n`);
    expect((await runScript(versionScript(path))).stdout.trim()).toBe('26.10.0');
  });

  it('pollScript refuse un identifiant de tâche qui n’en est pas un', () => {
    expect(() => pollScript({ envFile: '/h/env', taskId: 'a;rm' })).toThrow('identifiant');
  });
});

describe('dossier jetable distant : préparation, envoi, nettoyage', () => {
  it('prepareScript crée un dossier que isSafeRemoteDir reconnaît, cleanupScript le supprime', async () => {
    const made = await runScript(prepareScript(), { TMPDIR: scratch });
    const dir = made.stdout.trim();
    expect(isSafeRemoteDir(dir)).toBe(true);
    expect(await stat(dir).then((s) => s.isDirectory())).toBe(true);
    expect((await runScript(cleanupScript(dir))).code).toBe(0);
    expect(
      await stat(dir).then(
        () => true,
        () => false,
      ),
    ).toBe(false);
  });

  it('cleanupScript refuse tout chemin qui n’est pas un dossier jetable', () => {
    expect(() => cleanupScript('/home/u')).toThrow('dossier distant');
  });

  it('tarArgs + uploadCommand transportent exactement les chemins demandés', async () => {
    const source = join(scratch, 'source');
    await mkdir(join(source, 'src'), { recursive: true });
    await mkdir(join(source, 'reports', 'coverage-all'), { recursive: true });
    await writeFile(join(source, 'src', 'a.ts'), 'export const a = 1;\n');
    await writeFile(join(source, 'tsconfig.json'), '{}\n');
    await writeFile(join(source, 'reports', 'coverage-all', 'gros.json'), '{}');
    const target = join(scratch, 'prosperity-sonar.AbC123');
    await mkdir(target);
    const tar = await locate('tar');
    const code = await new Promise<number>((resolve) => {
      const maker = spawn(tar, tarArgs(source, ['src', 'tsconfig.json']), {
        stdio: ['ignore', 'pipe', 'ignore'],
      });
      const taker = spawn('/bin/sh', ['-c', uploadCommand(target)], {
        env: { PATH: bin },
        stdio: ['pipe', 'ignore', 'ignore'],
      });
      maker.stdout.pipe(taker.stdin);
      taker.on('close', (c) => {
        resolve(c ?? 1);
      });
    });
    expect(code).toBe(0);
    expect(await readFile(join(target, 'src', 'a.ts'), 'utf8')).toBe('export const a = 1;\n');
    expect(await readFile(join(target, 'tsconfig.json'), 'utf8')).toBe('{}\n');
    expect(
      await stat(join(target, 'reports')).then(
        () => true,
        () => false,
      ),
    ).toBe(false);
  });
});
