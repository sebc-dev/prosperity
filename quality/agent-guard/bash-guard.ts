export type Decision = { decision: 'allow' } | { decision: 'deny'; reason: string };

export function evaluateCommand(
  _command: string,
  _protectedGlobs: readonly string[],
  _cwd?: string,
): Decision {
  return { decision: 'allow' };
}
