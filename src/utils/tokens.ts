export function estimateTokens(value: unknown): number {
  const text = stringifyEventValue(value).trim();
  return text.length === 0 ? 0 : Math.max(1, Math.ceil(text.length / 4));
}

export function stringifyEventValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === null || value === undefined) return '';
  return JSON.stringify(value);
}
