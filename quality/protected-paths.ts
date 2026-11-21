export function loadProtectedPaths(
  _root: string,
): Promise<{ paths: string[]; agentExempt: string[] }> {
  return Promise.resolve({ paths: [], agentExempt: [] });
}

export function isProtected(_relPath: string, _globs: readonly string[]): boolean {
  return false;
}
