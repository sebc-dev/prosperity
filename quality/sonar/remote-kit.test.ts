import { describe, expect, it } from 'vitest';
import {
  isSafeRemoteDir,
  parsePreflight,
  shellQuote,
  sshInvocation,
  validateRemoteConfig,
} from './remote-kit.ts';

function errorOf(result: object): string {
  return 'error' in result && typeof result.error === 'string' ? result.error : '';
}

describe('validateRemoteConfig', () => {
  it('applique les défauts : hôte kfzserver, fichier sous le dossier personnel, Docker, couverture complète', () => {
    expect(validateRemoteConfig({})).toStrictEqual({
      sshHost: 'kfzserver',
      envFile: '.config/prosperity-sonar/env',
      engine: 'docker',
      coverage: 'full',
    });
  });

  it('accepte une cible user@hôte et un fichier d’environnement absolu', () => {
    const config = validateRemoteConfig({
      SONAR_SSH_HOST: 'negus@hote.example',
      SONAR_REMOTE_ENV_FILE: '/etc/prosperity/env',
      SONAR_CONTAINER_ENGINE: 'podman',
      SONAR_COVERAGE: 'unit',
    });
    expect(config).toStrictEqual({
      sshHost: 'negus@hote.example',
      envFile: '/etc/prosperity/env',
      engine: 'podman',
      coverage: 'unit',
    });
  });

  it.each([
    ['une option ssh', '-oProxyCommand=touch /data/x'],
    ['une espace', 'a b'],
    ['un point-virgule', 'hote;rm'],
    ['une cible vide', ''],
  ])('refuse un SONAR_SSH_HOST avec %s', (_name, host) => {
    expect(errorOf(validateRemoteConfig({ SONAR_SSH_HOST: host }))).toContain('SONAR_SSH_HOST');
  });

  it.each([
    ['..', '../env'],
    ['des espaces', 'a b/env'],
    ['un guillemet', "a'b"],
  ])('refuse un SONAR_REMOTE_ENV_FILE avec %s', (_name, path) => {
    expect(errorOf(validateRemoteConfig({ SONAR_REMOTE_ENV_FILE: path }))).toContain(
      'SONAR_REMOTE_ENV_FILE',
    );
  });

  it('refuse un moteur ou une couverture inconnus', () => {
    expect(errorOf(validateRemoteConfig({ SONAR_CONTAINER_ENGINE: 'nerdctl' }))).toContain(
      'moteur',
    );
    expect(errorOf(validateRemoteConfig({ SONAR_COVERAGE: 'tout' }))).toContain('SONAR_COVERAGE');
  });
});

describe('shellQuote, sshInvocation, isSafeRemoteDir', () => {
  it('shellQuote protège les apostrophes et la chaîne vide', () => {
    expect(shellQuote("it's")).toBe(`'it'\\''s'`);
    expect(shellQuote('')).toBe("''");
  });

  it('sshInvocation désactive les questions, borne la connexion et sépare l’hôte des options', () => {
    expect(sshInvocation('hote', 'sh -s')).toStrictEqual({
      command: 'ssh',
      args: ['-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '--', 'hote', 'sh -s'],
    });
  });

  it.each([
    ['/data/prosperity-sonar.AbC123', true],
    ['/var/lib/x/prosperity-sonar.AbC123', true],
    ['/', false],
    ['/data', false],
    ['/data/prosperity-sonar.AbC123; rm -rf ~', false],
    ['/data/../etc/prosperity-sonar.AbC123', false],
    ['/data/autre.AbC123', false],
    ['prosperity-sonar.AbC123', false],
  ])('isSafeRemoteDir(%s) : %s', (dir, safe) => {
    expect(isSafeRemoteDir(dir)).toBe(safe);
  });
});

describe('parsePreflight', () => {
  it('lit « ok <uid> <gid> <fichier> »', () => {
    expect(parsePreflight('ok 1000 1001 /home/u/.config/prosperity-sonar/env\n')).toStrictEqual({
      uid: 1000,
      gid: 1001,
      envFile: '/home/u/.config/prosperity-sonar/env',
    });
  });

  it.each([
    ['env-file-missing', 'introuvable'],
    ['env-file-mode', '0600'],
    ['env-file-keys', 'SONAR_TOKEN'],
    ['env-file-format', 'guillemet'],
    ['host-url-refused', 'SONAR_HOST_URL'],
    ['engine-missing', 'moteur'],
    ['engine-access', 'accès'],
  ])('traduit le code %s en message', (code, fragment) => {
    expect(errorOf(parsePreflight(`${code}\n`))).toContain(fragment);
  });

  it('refuse une sortie inattendue', () => {
    expect(errorOf(parsePreflight('bonjour'))).toContain('inattendue');
  });
});
