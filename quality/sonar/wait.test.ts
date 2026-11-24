import { describe, expect, it } from 'vitest';
import { waitForTask } from './wait.ts';

/** Horloge fictive : `sleep` fait avancer `now`, aucun vrai délai. */
function fakeClock(): {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  sleeps: number[];
} {
  let time = 0;
  const sleeps: number[] = [];
  return {
    now: () => time,
    sleep: (ms) => {
      sleeps.push(ms);
      time += ms;
      return Promise.resolve();
    },
    sleeps,
  };
}

const task = (status: string): unknown => ({ task: { status } });

describe('waitForTask', () => {
  it('attend que la tâche passe de PENDING à SUCCESS', async () => {
    const clock = fakeClock();
    const answers = [task('PENDING'), task('IN_PROGRESS'), task('SUCCESS')];
    const outcome = await waitForTask({
      fetchTask: () => Promise.resolve(answers.shift()),
      ...clock,
      intervalMs: 5000,
      timeoutMs: 600_000,
    });
    expect(outcome).toStrictEqual({ state: 'success', status: 'SUCCESS' });
    expect(clock.sleeps).toStrictEqual([5000, 5000]);
  });

  it('rend failed sans attendre quand la tâche est FAILED ou CANCELED', async () => {
    const clock = fakeClock();
    const outcome = await waitForTask({
      fetchTask: () => Promise.resolve(task('CANCELED')),
      ...clock,
      intervalMs: 5000,
      timeoutMs: 600_000,
    });
    expect(outcome).toStrictEqual({ state: 'failed', status: 'CANCELED' });
    expect(clock.sleeps).toStrictEqual([]);
  });
});

describe('waitForTask : délai et erreurs de lecture', () => {
  it('rend timeout quand la tâche reste en cours au-delà du délai', async () => {
    const clock = fakeClock();
    let calls = 0;
    const outcome = await waitForTask({
      fetchTask: () => {
        calls += 1;
        return Promise.resolve(task('IN_PROGRESS'));
      },
      ...clock,
      intervalMs: 1000,
      timeoutMs: 3500,
    });
    expect(outcome).toStrictEqual({ state: 'timeout', status: 'IN_PROGRESS' });
    expect(calls).toBe(4);
  });

  it('tolère une erreur de lecture isolée mais pas trois de suite', async () => {
    const clock = fakeClock();
    let calls = 0;
    const flaky = await waitForTask({
      fetchTask: () => {
        calls += 1;
        return calls === 1 ? Promise.reject(new Error('réseau')) : Promise.resolve(task('SUCCESS'));
      },
      ...clock,
      intervalMs: 10,
      timeoutMs: 1000,
    });
    expect(flaky).toStrictEqual({ state: 'success', status: 'SUCCESS' });
    const dead = await waitForTask({
      fetchTask: () => Promise.reject(new Error('réseau')),
      ...fakeClock(),
      intervalMs: 10,
      timeoutMs: 1000,
    });
    expect(dead).toStrictEqual({ state: 'failed', status: 'injoignable' });
  });
});
