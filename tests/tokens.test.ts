import { describe, expect, it } from 'vitest';
import { estimateTokens, stringifyEventValue } from '../src/utils/tokens.js';

describe('token estimation', () => {
  it('uses a one-token-per-four-chars heuristic', () => {
    expect(estimateTokens('abcd')).toBe(1);
    expect(estimateTokens('abcde')).toBe(2);
    expect(estimateTokens('')).toBe(0);
  });

  it('stringifies structured event values', () => {
    expect(stringifyEventValue({ tool: 'Read' })).toBe('{"tool":"Read"}');
  });
});
