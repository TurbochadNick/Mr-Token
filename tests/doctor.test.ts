import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { generateDoctorPatches } from '../src/doctor/patches.js';

describe('doctor patch generation', () => {
  it('writes safe patch proposals without modifying live files', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-doctor-'));
    const claudePath = join(projectRoot, 'CLAUDE.md');
    const settingsPath = join(projectRoot, '.claude', 'settings.local.json');
    const originalClaude = ['# Project', '', 'Keep this command: pnpm test.', 'Historical note. '.repeat(500)].join('\n');
    const originalSettings = JSON.stringify({ permissions: { allow: ['Bash(git status)'] } }, null, 2);
    writeFileSync(claudePath, originalClaude, 'utf8');
    mkdirSync(join(projectRoot, '.claude'), { recursive: true });
    writeFileSync(settingsPath, originalSettings, 'utf8');

    const result = generateDoctorPatches(projectRoot, new Date(2026, 4, 25, 10, 11, 12));

    expect(result.patchDir.endsWith('.token-tithe/patches/20260525-101112')).toBe(true);
    expect(readFileSync(claudePath, 'utf8')).toBe(originalClaude);
    expect(readFileSync(settingsPath, 'utf8')).toBe(originalSettings);
    expect(existsSync(join(result.patchDir, 'CLAUDE.md'))).toBe(true);
    expect(existsSync(join(result.patchDir, '.claude', 'skills', 'token-efficient-project', 'SKILL.md'))).toBe(true);
    expect(existsSync(join(result.patchDir, '.claude', 'commands', 'audit-context.md'))).toBe(true);
    expect(existsSync(join(result.patchDir, '.claude', 'settings.local.json'))).toBe(true);
    expect(existsSync(result.diffPath)).toBe(true);
    expect(existsSync(result.summaryPath)).toBe(true);
  });

  it('summarizes proposed changes and hook improvements', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-doctor-'));
    const result = generateDoctorPatches(projectRoot, new Date(2026, 4, 25, 10, 11, 12));
    const summary = readFileSync(result.summaryPath, 'utf8');
    const diff = readFileSync(result.diffPath, 'utf8');
    const proposedSettings = readFileSync(join(result.patchDir, '.claude', 'settings.local.json'), 'utf8');

    expect(summary).toContain('These files are proposals only.');
    expect(summary).toContain('ADD .claude/skills/token-efficient-project/SKILL.md');
    expect(summary).toContain('ADD .claude/commands/audit-context.md');
    expect(diff).toContain('diff --git a/CLAUDE.md b/CLAUDE.md');
    expect(proposedSettings).toContain('UserPromptSubmit');
    expect(proposedSettings).toContain('PreCompact');
    expect(proposedSettings).toContain('token-tithe watch --stdin');
  });
});
