import { ceTaskDecision } from './sonar-kit.ts';

export interface WaitOptions {
  fetchTask: () => Promise<unknown>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  intervalMs: number;
  timeoutMs: number;
}

export interface WaitOutcome {
  state: 'success' | 'failed' | 'timeout';
  status: string;
}

const MAX_CONSECUTIVE_READ_ERRORS = 3;

/**
 * Interroge la tâche du serveur jusqu'à un état final ou au délai. Une erreur de lecture isolée
 * (réseau) est tolérée ; trois de suite donnent `injoignable`.
 */
export async function waitForTask(options: WaitOptions): Promise<WaitOutcome> {
  const start = options.now();
  let status = 'inconnu';
  let readErrors = 0;
  while (options.now() - start < options.timeoutMs) {
    try {
      const decision = ceTaskDecision(await options.fetchTask());
      readErrors = 0;
      status = decision.status;
      if (decision.state !== 'pending') {
        return { state: decision.state, status };
      }
    } catch {
      readErrors += 1;
      if (readErrors >= MAX_CONSECUTIVE_READ_ERRORS) {
        return { state: 'failed', status: 'injoignable' };
      }
    }
    await options.sleep(options.intervalMs);
  }
  return { state: 'timeout', status };
}
