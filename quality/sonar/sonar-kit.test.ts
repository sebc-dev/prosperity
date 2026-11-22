import { describe, expect, it } from 'vitest';
import { isRecord } from '../tools.ts';
import {
  ceTaskDecision,
  childEnv,
  forbiddenProperties,
  parseEnvFile,
  parseReportTask,
  readScannerImage,
  redactInvocation,
  relativizeEslintReport,
  relativizeLcov,
  scannerInvocation,
  validateSonarConfig,
} from './sonar-kit.ts';
import type { SonarConfig } from './sonar-kit.ts';

// Jeton factice : jamais au format des jetons Sonar (préfixe `sq` + lettre + souligné + 40 hexadécimaux).
const JETON = 'jeton-factice-0123';
const DIGEST = 'ab'.repeat(32);
const IMAGE = `docker.io/sonarsource/sonar-scanner-cli:12.1@sha256:${DIGEST}`;
const HTTPS = { SONAR_HOST_URL: 'https://sonar.example', SONAR_TOKEN: JETON };

function errorOf(result: unknown): string {
  return isRecord(result) && typeof result['error'] === 'string' ? result['error'] : '';
}

describe('parseEnvFile', () => {
  it('lit CLÉ=valeur et ignore lignes vides et commentaires', () => {
    const text = '# commentaire\n\nSONAR_HOST_URL=https://sonar.example\n  SONAR_TOKEN=abc\n';
    expect(parseEnvFile(text)).toStrictEqual({
      SONAR_HOST_URL: 'https://sonar.example',
      SONAR_TOKEN: 'abc',
    });
  });

  it('retire une paire de guillemets autour de la valeur, et elle seule', () => {
    expect(parseEnvFile(`A="x y"\nB='z'\nC="mismatch'\nD=b=c\r\n`)).toStrictEqual({
      A: 'x y',
      B: 'z',
      C: `"mismatch'`,
      D: 'b=c',
    });
  });
});

describe('validateSonarConfig', () => {
  it('accepte https, retire la barre oblique finale et applique les défauts (Podman d’abord)', () => {
    const config = validateSonarConfig({ ...HTTPS, SONAR_HOST_URL: 'https://sonar.example/' }, [
      'docker',
      'podman',
    ]);
    expect(config).toStrictEqual({
      hostUrl: 'https://sonar.example',
      token: JETON,
      coverage: 'full',
      engine: 'podman',
    });
  });

  it.each([
    ['absent', undefined],
    ['vide', ''],
    ['sans schéma', 'sonar.example'],
    ['porteur d’une requête', 'https://sonar.example/?x=1'],
    ['en http hors boucle locale', 'http://sonar.example'],
    ['en http sur un nom qui commence par localhost', 'http://localhost.example'],
  ])('refuse un SONAR_HOST_URL %s', (_name, host) => {
    const vars = host === undefined ? { SONAR_TOKEN: JETON } : { ...HTTPS, SONAR_HOST_URL: host };
    expect(errorOf(validateSonarConfig(vars, ['docker']))).toContain('SONAR_HOST_URL');
  });

  it('autorise http sur la boucle locale (serveur local du homelab) et sur un hôte avec SONAR_ALLOW_INSECURE_HTTP=1', () => {
    const local = validateSonarConfig({ ...HTTPS, SONAR_HOST_URL: 'http://localhost:9000' }, [
      'docker',
    ]);
    const tailnet = validateSonarConfig(
      { ...HTTPS, SONAR_HOST_URL: 'http://sonar.example:9000', SONAR_ALLOW_INSECURE_HTTP: '1' },
      ['docker'],
    );
    expect(local).toStrictEqual({
      hostUrl: 'http://localhost:9000',
      token: JETON,
      coverage: 'full',
      engine: 'docker',
    });
    expect(tailnet).toHaveProperty('hostUrl', 'http://sonar.example:9000');
  });
});

describe('validateSonarConfig : jeton, couverture et moteur', () => {
  it.each([
    ['absent', undefined],
    ['vide', ''],
    ['avec une espace', 'a b'],
  ])('refuse un SONAR_TOKEN %s sans jamais le citer', (_name, token) => {
    const vars =
      token === undefined
        ? { SONAR_HOST_URL: HTTPS.SONAR_HOST_URL }
        : { ...HTTPS, SONAR_TOKEN: token };
    const message = errorOf(validateSonarConfig(vars, ['docker']));
    expect(message).toContain('SONAR_TOKEN');
    expect(message).not.toContain('a b');
  });

  it('refuse SONAR_COVERAGE hors full|unit et accepte unit', () => {
    expect(
      errorOf(validateSonarConfig({ ...HTTPS, SONAR_COVERAGE: 'tout' }, ['docker'])),
    ).toContain('SONAR_COVERAGE');
    expect(validateSonarConfig({ ...HTTPS, SONAR_COVERAGE: 'unit' }, ['docker'])).toHaveProperty(
      'coverage',
      'unit',
    );
  });

  it('refuse un moteur demandé absent des moteurs trouvés, et l’absence de tout moteur', () => {
    const asked = { ...HTTPS, SONAR_CONTAINER_ENGINE: 'podman' };
    expect(errorOf(validateSonarConfig(asked, ['docker']))).toContain('podman');
    expect(errorOf(validateSonarConfig(HTTPS, []))).toContain('moteur');
  });
});

describe('readScannerImage', () => {
  it('accepte l’image officielle épinglée par digest', () => {
    expect(readScannerImage({ image: IMAGE, tag: '12.1', published: '2026-11-09' })).toStrictEqual({
      image: IMAGE,
    });
  });

  it.each([
    ['sans digest', 'docker.io/sonarsource/sonar-scanner-cli:12.1'],
    ['latest', `docker.io/sonarsource/sonar-scanner-cli:latest@sha256:${DIGEST}`],
    ['autre dépôt', `docker.io/autre/sonar-scanner-cli:12.1@sha256:${DIGEST}`],
    ['digest court', 'docker.io/sonarsource/sonar-scanner-cli:12.1@sha256:abcd'],
  ])('refuse une image %s', (_name, image) => {
    expect(errorOf(readScannerImage({ image }))).toContain('image');
  });

  it('refuse un contenu qui n’est pas un objet avec une image', () => {
    expect(errorOf(readScannerImage(['x']))).toContain('image');
    expect(errorOf(readScannerImage({ tag: '12.1' }))).toContain('image');
  });
});

describe('forbiddenProperties', () => {
  it('rend une liste vide pour un fichier propre', () => {
    expect(
      forbiddenProperties('# note\nsonar.projectKey=prosperity\nsonar.sources=src\n'),
    ).toStrictEqual([]);
  });

  it.each([
    ['sonar.host.url=https://x', 'sonar.host.url'],
    ['  sonar.token = x', 'sonar.token'],
    ['sonar.login: u', 'sonar.login'],
    ['sonar.password=p', 'sonar.password'],
    ['sonar.scanner.proxyHost=h', 'sonar.scanner.proxyHost'],
    ['http.proxyHost=h', 'http.proxyHost'],
  ])('signale « %s »', (line, key) => {
    expect(forbiddenProperties(`sonar.projectKey=prosperity\n${line}\n`)).toStrictEqual([key]);
  });

  it('ignore une clé interdite en commentaire', () => {
    expect(forbiddenProperties('# sonar.token=x\n! sonar.login=y\n')).toStrictEqual([]);
  });
});

describe('chemins relatifs des rapports', () => {
  it('relativizeLcov ne réécrit que les fichiers sous la racine', () => {
    const text = 'SF:/work/p/src/a.ts\nDA:1,1\nSF:/work/p-autre/b.ts\nSF:/ailleurs/c.ts\n';
    expect(relativizeLcov(text, '/work/p')).toBe(
      'SF:src/a.ts\nDA:1,1\nSF:/work/p-autre/b.ts\nSF:/ailleurs/c.ts\n',
    );
  });

  it('relativizeEslintReport ne réécrit que les filePath sous la racine', () => {
    const report = [
      { filePath: '/work/p/src/a.ts', messages: [], errorCount: 0 },
      { filePath: '/ailleurs/c.ts', messages: [] },
      'inattendu',
    ];
    expect(relativizeEslintReport(report, '/work/p')).toStrictEqual([
      { filePath: 'src/a.ts', messages: [], errorCount: 0 },
      { filePath: '/ailleurs/c.ts', messages: [] },
      'inattendu',
    ]);
    expect(relativizeEslintReport({ a: 1 }, '/work/p')).toStrictEqual({ a: 1 });
  });
});

describe('childEnv', () => {
  it('retire SONAR_TOKEN et SONAR_HOST_URL et garde le reste', () => {
    const env = { PATH: '/usr/bin', SONAR_TOKEN: JETON, SONAR_HOST_URL: 'https://s', HOME: '/h' };
    expect(childEnv(env)).toStrictEqual({ PATH: '/usr/bin', HOME: '/h' });
  });
});

describe('scannerInvocation et redactInvocation', () => {
  const cfg: SonarConfig = {
    hostUrl: 'https://sonar.example',
    token: JETON,
    coverage: 'unit',
    engine: 'docker',
  };
  const opts = { image: IMAGE, root: '/work/p', uid: 1000, gid: 1001, scmDisabled: false };

  it('compose l’appel Docker : utilisateur, environnement sans valeur, sources montées', () => {
    const inv = scannerInvocation(cfg, opts);
    expect(inv.command).toBe('docker');
    expect(inv.args).toStrictEqual([
      'run',
      '--rm',
      '--network',
      'host',
      '--user',
      '1000:1001',
      '-e',
      'SONAR_HOST_URL',
      '-e',
      'SONAR_TOKEN',
      '-e',
      'SONAR_USER_HOME=/usr/src/reports/sonar/cache',
      '-v',
      '/work/p:/usr/src',
      IMAGE,
      '-Dsonar.host.url=https://sonar.example',
      '-Dsonar.analysis.coverage=unit',
    ]);
    expect(inv.env).toStrictEqual({ SONAR_HOST_URL: 'https://sonar.example', SONAR_TOKEN: JETON });
  });

  it('n’expose jamais la valeur du jeton dans les arguments', () => {
    expect(scannerInvocation(cfg, opts).args.join(' ')).not.toContain(JETON);
  });

  it('utilise --userns=keep-id pour Podman et désactive Git à la demande', () => {
    const inv = scannerInvocation({ ...cfg, engine: 'podman' }, { ...opts, scmDisabled: true });
    expect(inv.command).toBe('podman');
    expect(inv.args).toContain('--userns=keep-id');
    expect(inv.args).not.toContain('--user');
    expect(inv.args.at(-1)).toBe('-Dsonar.scm.disabled=true');
  });

  it('redactInvocation remplace toute occurrence du jeton par ***', () => {
    const inv = { command: 'docker', args: ['run', `-Dx=${JETON}`, `${JETON}${JETON}`] };
    expect(redactInvocation(inv, JETON)).toBe('docker run -Dx=*** ******');
  });

  it('redactInvocation laisse l’invocation intacte quand il n’y a pas de jeton', () => {
    expect(redactInvocation({ command: 'docker', args: ['run', 'x'] }, '')).toBe('docker run x');
  });
});

describe('parseReportTask', () => {
  it('lit ceTaskId dans report-task.txt', () => {
    expect(
      parseReportTask('projectKey=prosperity\r\nceTaskId=AZ12-ab_c\nserverUrl=http://x\n'),
    ).toStrictEqual({
      ceTaskId: 'AZ12-ab_c',
    });
  });

  it('rend undefined quand ceTaskId est absent ou contient autre chose qu’un identifiant', () => {
    expect(parseReportTask('projectKey=prosperity\n')).toBeUndefined();
    expect(parseReportTask('ceTaskId=a;rm -rf /\n')).toBeUndefined();
  });
});

describe('ceTaskDecision', () => {
  it.each([
    ['SUCCESS', 'success'],
    ['PENDING', 'pending'],
    ['IN_PROGRESS', 'pending'],
    ['FAILED', 'failed'],
    ['CANCELED', 'failed'],
    ['INCONNU', 'failed'],
  ])('statut %s : %s', (status, state) => {
    expect(ceTaskDecision({ task: { status } })).toStrictEqual({ state, status });
  });

  it('refuse une réponse sans statut', () => {
    expect(ceTaskDecision({})).toStrictEqual({ state: 'failed', status: 'illisible' });
  });
});
