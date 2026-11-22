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

// Squelette du cycle RED : signature finale, comportement volontairement absent.
export function waitForTask(options: WaitOptions): Promise<WaitOutcome> {
  return Promise.resolve({ state: 'timeout', status: String(options.timeoutMs) });
}
