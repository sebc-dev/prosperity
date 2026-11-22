import { describe, expect, it } from 'vitest';
import { clearRepoGitVariables } from './tools.ts';

describe('clearRepoGitVariables', () => {
  it('retire les variables git qui désignent le dépôt de l’appelant', () => {
    const env: NodeJS.ProcessEnv = {
      GIT_DIR: '/depot/.git/worktrees/agent',
      GIT_WORK_TREE: '/depot/agent',
      GIT_COMMON_DIR: '/depot/.git',
      GIT_OBJECT_DIRECTORY: '/depot/.git/objects',
      GIT_ALTERNATE_OBJECT_DIRECTORIES: '/autre/objects',
      GIT_NAMESPACE: 'ns',
      GIT_PREFIX: 'quality/',
      GIT_QUARANTINE_PATH: '/depot/.git/objects/incoming',
      PATH: '/usr/bin',
    };
    clearRepoGitVariables(env);
    expect(env).toStrictEqual({ PATH: '/usr/bin' });
  });

  it('garde l’identité git, l’index du commit en cours et le reste de l’environnement', () => {
    const env: NodeJS.ProcessEnv = {
      GIT_AUTHOR_NAME: 't',
      GIT_INDEX_FILE: '/depot/.git/index.lock',
      GIT_TERMINAL_PROMPT: '0',
      HOME: '/home/t',
    };
    clearRepoGitVariables(env);
    expect(env).toStrictEqual({
      GIT_AUTHOR_NAME: 't',
      GIT_INDEX_FILE: '/depot/.git/index.lock',
      GIT_TERMINAL_PROMPT: '0',
      HOME: '/home/t',
    });
  });
});
