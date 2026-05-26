import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { mergeTokenTitheHooks, type ClaudeSettings } from '../adapters/claude-code/install.js';
import { defaultClaudeSettingsPath, defaultDataDir, defaultDbPath, defaultEventsPath } from '../utils/paths.js';

export type DoctorPatchFile = {
  targetPath: string;
  patchPath: string;
  status: 'add' | 'modify';
  summary: string;
};

export type DoctorPatchResult = {
  patchDir: string;
  files: DoctorPatchFile[];
  diffPath: string;
  summaryPath: string;
};

export function generateDoctorPatches(
  projectRoot: string,
  now = new Date(),
  options: { dbPath?: string; settingsPath?: string } = {}
): DoctorPatchResult {
  const patchDir = join(defaultDataDir(projectRoot), 'patches', timestampForPath(now));
  mkdirSync(patchDir, { recursive: true });

  const dbPath = options.dbPath ?? defaultDbPath(projectRoot);
  const eventsPath = defaultEventsPath(projectRoot);
  const settingsPath = options.settingsPath ?? defaultClaudeSettingsPath(projectRoot);
  const proposals = [
    proposeClaudeMd(projectRoot),
    proposeSkill(projectRoot),
    proposeAuditContextCommand(projectRoot),
    proposeSettings(projectRoot, settingsPath, dbPath, eventsPath)
  ];
  const files: DoctorPatchFile[] = [];
  const diffChunks: string[] = [];

  for (const proposal of proposals) {
    const patchPath = join(patchDir, relative(projectRoot, proposal.targetPath));
    mkdirSync(dirname(patchPath), { recursive: true });
    writeFileSync(patchPath, proposal.content, 'utf8');

    const existing = existsSync(proposal.targetPath) ? readFileSync(proposal.targetPath, 'utf8') : '';
    files.push({
      targetPath: proposal.targetPath,
      patchPath,
      status: existsSync(proposal.targetPath) ? 'modify' : 'add',
      summary: proposal.summary
    });
    diffChunks.push(formatUnifiedDiff(relative(projectRoot, proposal.targetPath), existing, proposal.content));
  }

  const diffPath = join(patchDir, 'patch.diff');
  const summaryPath = join(patchDir, 'SUMMARY.md');
  writeFileSync(diffPath, `${diffChunks.join('\n')}\n`, 'utf8');
  writeFileSync(summaryPath, formatPatchSummary(projectRoot, patchDir, files), 'utf8');

  return { patchDir, files, diffPath, summaryPath };
}

function proposeClaudeMd(projectRoot: string): { targetPath: string; content: string; summary: string } {
  const targetPath = join(projectRoot, 'CLAUDE.md');
  const existing = existsSync(targetPath) ? readFileSync(targetPath, 'utf8') : '';
  const content = compressClaudeMd(existing);

  return {
    targetPath,
    content,
    summary: existing ? 'Compress CLAUDE.md into a shorter guidance file.' : 'Create a concise CLAUDE.md starter.'
  };
}

function compressClaudeMd(existing: string): string {
  const sourceLines = existing.split(/\r?\n/);
  const selected: string[] = [];
  const seen = new Set<string>();

  for (const rawLine of sourceLines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) continue;

    const useful =
      trimmed.startsWith('#') ||
      trimmed.startsWith('-') ||
      trimmed.startsWith('*') ||
      trimmed.startsWith('1.') ||
      /\b(test|build|lint|typecheck|run|avoid|prefer|must|never|architecture|command|workflow)\b/i.test(trimmed);
    const key = trimmed.toLowerCase().replace(/\s+/g, ' ');

    if (!useful || seen.has(key)) continue;
    seen.add(key);
    selected.push(line);

    if (selected.length >= 80 || selected.join('\n').length >= 6000) break;
  }

  const body = selected.length > 0 ? selected.join('\n') : '- Keep guidance short, current, and project-specific.';

  return [
    '# CLAUDE.md',
    '',
    '<!-- Proposed by token-tithe doctor. Review before replacing the live file. -->',
    '',
    '## Token-Efficient Project Guidance',
    '',
    body,
    '',
    '## Maintenance',
    '',
    '- Keep this file under roughly 1,500 tokens.',
    '- Move long examples, historical notes, and rarely used details into linked docs.',
    '- Prefer exact commands and project constraints over broad prose.',
    ''
  ].join('\n');
}

function proposeSkill(projectRoot: string): { targetPath: string; content: string; summary: string } {
  const targetPath = join(projectRoot, '.claude', 'skills', 'token-efficient-project', 'SKILL.md');
  const content = [
    '# Token-Efficient Project',
    '',
    'Use this skill when working in this repository and context size, tool output, or repeated prompts are becoming expensive.',
    '',
    '## Workflow',
    '',
    '- Read only the files and line ranges needed for the current task.',
    '- Search before opening large files.',
    '- Prefer concise command output and failure-focused logs.',
    '- Reuse project guidance instead of repeating long prompt blocks.',
    '- Compact after meaningful milestones, not only when context is nearly full.',
    '',
    '## Before Large Tool Calls',
    '',
    '- State the exact file, symbol, or behavior being inspected.',
    '- Avoid broad recursive reads unless the result will directly change the next action.',
    '- Redirect bulky output to a file and inspect targeted excerpts.',
    ''
  ].join('\n');

  return { targetPath, content, summary: 'Create a Claude skill for token-efficient project work.' };
}

function proposeAuditContextCommand(projectRoot: string): { targetPath: string; content: string; summary: string } {
  const targetPath = join(projectRoot, '.claude', 'commands', 'audit-context.md');
  const content = [
    '# /audit-context',
    '',
    'Review the current Claude Code session for token waste and summarize the next safest reductions.',
    '',
    'Run locally:',
    '',
    '```bash',
    'token-tithe audit',
    '```',
    '',
    'Then report:',
    '',
    '- top waste categories',
    '- exact evidence lines',
    '- fixes to apply manually',
    '- what should not be changed',
    ''
  ].join('\n');

  return { targetPath, content, summary: 'Create an /audit-context custom slash command.' };
}

function proposeSettings(
  projectRoot: string,
  settingsPath: string,
  dbPath: string,
  eventsPath: string
): { targetPath: string; content: string; summary: string } {
  const settings = readSettings(settingsPath);
  const nextSettings = mergeTokenTitheHooks(settings, dbPath, eventsPath);
  const content = `${JSON.stringify(nextSettings, null, 2)}\n`;

  return {
    targetPath: settingsPath,
    content,
    summary: `Suggest hook improvements for ${relative(projectRoot, settingsPath)}.`
  };
}

function readSettings(settingsPath: string): ClaudeSettings {
  try {
    return JSON.parse(readFileSync(settingsPath, 'utf8')) as ClaudeSettings;
  } catch {
    return {};
  }
}

function formatPatchSummary(projectRoot: string, patchDir: string, files: DoctorPatchFile[]): string {
  return [
    '# token-tithe doctor patch bundle',
    '',
    `Project root: ${projectRoot}`,
    `Patch directory: ${patchDir}`,
    '',
    'These files are proposals only. Review them manually before applying.',
    '',
    '## Diff Summary',
    '',
    ...files.map((file) => `- ${file.status.toUpperCase()} ${relative(projectRoot, file.targetPath)}: ${file.summary}`),
    '',
    '## Manual Review',
    '',
    '- Compare proposed files with the live project files.',
    '- Copy only the changes you want to apply.',
    '- Re-run `token-tithe doctor` after applying changes.',
    ''
  ].join('\n');
}

function formatUnifiedDiff(relativePath: string, before: string, after: string): string {
  const beforeLines = before.split(/\r?\n/);
  const afterLines = after.split(/\r?\n/);
  const lines = [`diff --git a/${relativePath} b/${relativePath}`, `--- a/${relativePath}`, `+++ b/${relativePath}`, '@@'];
  const max = Math.max(beforeLines.length, afterLines.length);

  for (let index = 0; index < max; index += 1) {
    const oldLine = beforeLines[index];
    const newLine = afterLines[index];

    if (oldLine === newLine && oldLine !== undefined) {
      lines.push(` ${oldLine}`);
      continue;
    }

    if (oldLine !== undefined) lines.push(`-${oldLine}`);
    if (newLine !== undefined) lines.push(`+${newLine}`);
  }

  return lines.join('\n');
}

function timestampForPath(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds())
  ].join('');
}
