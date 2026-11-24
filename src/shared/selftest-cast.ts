export function parseCount(text: string): number {
  const value = JSON.parse(text) as { count: number };
  return value.count;
}
