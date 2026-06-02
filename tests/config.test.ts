import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadTokenTitheConfig } from '../src/config.js';

describe('token-tithe config', () => {
  it('defaults to AI disabled with redaction enabled', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-config-'));

    expect(loadTokenTitheConfig(projectRoot)).toEqual({
      ai: {
        enabled: false,
        model: 'claude-haiku-4-5',
        redaction: true,
        fullContext: false
      }
    });
  });

  it('reads tokenTithe.ai from package.json', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-config-'));
    mkdirSync(projectRoot, { recursive: true });
    writeFileSync(
      join(projectRoot, 'package.json'),
      JSON.stringify({
        tokenTithe: {
          ai: {
            enabled: true,
            model: 'claude-haiku-4-5',
            redaction: true
          }
        }
      }),
      'utf8'
    );

    expect(loadTokenTitheConfig(projectRoot).ai).toEqual({
      enabled: true,
      model: 'claude-haiku-4-5',
      redaction: true,
      fullContext: false
    });
  });
});
