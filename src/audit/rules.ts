import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { StoredEvent } from '../schemas/events.js';
import { estimateTokens } from '../utils/tokens.js';

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export type AuditFinding = {
  category: string;
  confidence: ConfidenceLevel;
  estimatedWasteTokens: number;
  savingsRange: [number, number];
  evidence: string[];
  recommendedFixes: string[];
};

export type AuditRuleContext = {
  events: StoredEvent[];
  projectRoot?: string;
};

export function runAuditRules(context: AuditRuleContext): AuditFinding[] {
  const findings = [
    detectBloatedClaudeMd(context),
    detectRepeatedPromptBlocks(context.events),
    detectLargeFileReads(context.events),
    detectHugeToolOutputs(context.events),
    detectExpensiveMcpUsage(context.events),
    detectExcessiveSubagents(context.events),
    detectLateCompaction(context.events),
    detectBroadUnscopedPrompts(context.events),
    detectModelMismatch(context.events)
  ].filter((finding): finding is AuditFinding => finding !== null);

  return findings.sort((a, b) => b.estimatedWasteTokens - a.estimatedWasteTokens || a.category.localeCompare(b.category));
}

function detectBloatedClaudeMd(context: AuditRuleContext): AuditFinding | null {
  const projectRoots = unique([
    context.projectRoot,
    ...context.events.map((event) => event.projectPath ?? undefined)
  ]);

  for (const projectRoot of projectRoots) {
    const claudePath = join(projectRoot, 'CLAUDE.md');
    if (!existsSync(claudePath)) continue;

    const text = readFileSync(claudePath, 'utf8');
    const tokens = estimateTokens(text);
    const lineCount = text.split(/\r?\n/).length;

    if (tokens < 3000) continue;

    const waste = Math.round(tokens * 0.45);
    return {
      category: 'Bloated CLAUDE.md',
      confidence: tokens >= 6000 ? 'high' : 'medium',
      estimatedWasteTokens: waste,
      savingsRange: [Math.round(waste * 0.5), Math.round(waste * 0.9)],
      evidence: [`${claudePath}:1 ${lineCount} lines, ${tokens.toLocaleString()} estimated tokens`],
      recommendedFixes: [
        'Move rarely used project notes out of CLAUDE.md.',
        'Keep only current commands, architecture constraints, and recurring preferences.',
        'Replace long examples with links to local docs.'
      ]
    };
  }

  return null;
}

function detectRepeatedPromptBlocks(events: StoredEvent[]): AuditFinding | null {
  const groups = new Map<string, StoredEvent[]>();

  for (const event of events) {
    if (!event.promptText || event.promptLength < 120) continue;
    const key = normalizeText(event.promptText);
    const group = groups.get(key) ?? [];
    group.push(event);
    groups.set(key, group);
  }

  const repeated = [...groups.values()].filter((group) => group.length >= 2);
  if (repeated.length === 0) return null;

  const evidence = repeated.flatMap((group) =>
    group.slice(0, 4).map((event) => `event #${event.id}: repeated prompt, ${event.estimatedTokens} tokens`)
  );
  const waste = repeated.reduce((sum, group) => sum + group.slice(1).reduce((inner, event) => inner + event.estimatedTokens, 0), 0);

  return {
    category: 'Repeated prompt blocks',
    confidence: 'high',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.6), waste],
    evidence,
    recommendedFixes: [
      'Move stable instructions into CLAUDE.md or a short command template.',
      'Reference prior context instead of pasting the same block again.'
    ]
  };
}

function detectLargeFileReads(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter(
    (event) =>
      isTool(event, ['Read', 'Grep', 'Glob']) &&
      (event.resultLength >= 20000 || event.estimatedTokens >= 5000)
  );
  if (hits.length === 0) return null;

  const waste = Math.round(sumTokens(hits) * 0.4);
  return {
    category: 'Large file reads',
    confidence: 'high',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.5), Math.round(waste * 1.1)],
    evidence: hits.slice(0, 6).map((event) => eventEvidence(event, `${event.filePath ?? 'unknown file'} read ${event.resultLength} chars`)),
    recommendedFixes: [
      'Read smaller line ranges instead of entire files.',
      'Use search first, then open only the relevant section.',
      'Summarize large files once and reuse the summary.'
    ]
  };
}

function detectHugeToolOutputs(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter((event) => outputLength(event) >= 16000);
  if (hits.length === 0) return null;

  const waste = Math.round(sumTokens(hits) * 0.5);
  return {
    category: 'Huge bash/tool outputs',
    confidence: 'high',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.5), Math.round(waste * 1.2)],
    evidence: hits.slice(0, 6).map((event) => eventEvidence(event, `${event.toolName ?? 'tool'} output ${outputLength(event)} chars`)),
    recommendedFixes: [
      'Pipe long commands through focused filters.',
      'Limit test logs to failures or final summaries.',
      'Redirect bulky artifacts to files and inspect targeted excerpts.'
    ]
  };
}

function detectExpensiveMcpUsage(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter((event) => {
    const raw = parseRaw(event);
    const tool = event.toolName?.toLowerCase() ?? '';
    const isMcp = tool.includes('mcp') || raw.server_name !== undefined || raw.mcp_server !== undefined;
    return isMcp && event.estimatedTokens >= 1500;
  });
  if (hits.length === 0) return null;

  const waste = Math.round(sumTokens(hits) * 0.35);
  return {
    category: 'Unused or expensive MCP/tool usage',
    confidence: 'medium',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.35), Math.round(waste * 0.85)],
    evidence: hits.slice(0, 6).map((event) => eventEvidence(event, `${event.toolName ?? 'MCP tool'} cost ${event.estimatedTokens} tokens`)),
    recommendedFixes: [
      'Call MCP tools only after local context is insufficient.',
      'Prefer narrow tool queries over broad workspace or document pulls.',
      'Cache useful MCP results in local notes when they will be reused.'
    ]
  };
}

function detectExcessiveSubagents(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter((event) => {
    const tool = event.toolName?.toLowerCase() ?? '';
    const raw = JSON.stringify(parseRaw(event)).toLowerCase();
    return tool === 'task' || tool.includes('subagent') || raw.includes('subagent') || raw.includes('spawn_agent');
  });
  if (hits.length < 3 && sumTokens(hits) < 6000) return null;

  const waste = Math.round(sumTokens(hits) * 0.3);
  return {
    category: 'Excessive subagent/task usage',
    confidence: hits.length >= 5 ? 'high' : 'medium',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.35), Math.round(waste * 0.8)],
    evidence: hits.slice(0, 6).map((event) => eventEvidence(event, `${event.toolName ?? 'Task'} event, ${event.estimatedTokens} tokens`)),
    recommendedFixes: [
      'Batch related exploration into one bounded task.',
      'Use subagents for parallel independent work, not serial context gathering.',
      'Give subagents smaller write scopes and explicit output requirements.'
    ]
  };
}

function detectLateCompaction(events: StoredEvent[]): AuditFinding | null {
  const compactIndex = events.findIndex((event) => event.eventType === 'PreCompact' || event.eventType === 'PostCompact');
  if (compactIndex < 0) return null;

  const tokensBeforeCompact = sumTokens(events.slice(0, compactIndex + 1));
  if (tokensBeforeCompact < 40000) return null;

  const compactEvent = events[compactIndex];
  const waste = Math.round(tokensBeforeCompact * 0.2);
  return {
    category: 'Late compaction',
    confidence: tokensBeforeCompact >= 80000 ? 'high' : 'medium',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.4), Math.round(waste * 0.9)],
    evidence: [eventEvidence(compactEvent, `first compaction after ${tokensBeforeCompact.toLocaleString()} estimated tokens`)],
    recommendedFixes: [
      'Compact after major milestones instead of near context exhaustion.',
      'Ask for a concise working summary before long implementation phases.'
    ]
  };
}

function detectBroadUnscopedPrompts(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter((event) => {
    const prompt = event.promptText?.toLowerCase() ?? '';
    if (!prompt) return false;
    const broadVerb = /\b(fix|improve|clean up|refactor|analyze|review|build|implement)\b/.test(prompt);
    const scoped = /(\b(src|tests|docs|package\.json|readme|\.ts|\.tsx|\.js|\.py)\b|#[0-9]+|\/)/i.test(prompt);
    return broadVerb && !scoped && event.promptLength <= 500;
  });
  if (hits.length === 0) return null;

  const waste = Math.round(sumTokens(hits) * 0.35);
  return {
    category: 'Broad unscoped prompts',
    confidence: 'medium',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.25), Math.round(waste * 0.75)],
    evidence: hits.slice(0, 6).map((event) => eventEvidence(event, preview(event.promptText ?? ''))),
    recommendedFixes: [
      'Name files, modules, or exact behavior in the prompt.',
      'State what should remain unchanged.',
      'Split discovery and implementation prompts when the target is unclear.'
    ]
  };
}

function detectModelMismatch(events: StoredEvent[]): AuditFinding | null {
  const hits = events.filter((event) => {
    const raw = parseRaw(event);
    const model = String(raw.model ?? raw.model_name ?? '').toLowerCase();
    const prompt = event.promptText?.toLowerCase() ?? '';
    const expensive = model.includes('opus') || model.includes('max') || model.includes('gpt-5') || model.includes('sonnet-4.5');
    const cheapMeta = /\b(status|summarize|rename|format|lint|commit message|explain this error|list files)\b/.test(prompt);
    return expensive && cheapMeta && event.promptLength > 0 && event.promptLength < 700;
  });
  if (hits.length === 0) return null;

  const waste = Math.round(sumTokens(hits) * 0.5);
  return {
    category: 'Model mismatch for cheap meta work',
    confidence: 'medium',
    estimatedWasteTokens: waste,
    savingsRange: [Math.round(waste * 0.4), Math.round(waste * 0.9)],
    evidence: hits.slice(0, 6).map((event) => {
      const raw = parseRaw(event);
      return eventEvidence(event, `${String(raw.model ?? raw.model_name)} used for "${preview(event.promptText ?? '')}"`);
    }),
    recommendedFixes: [
      'Use a cheaper model for summaries, status checks, formatting, and commit messages.',
      'Reserve expensive models for ambiguous architecture, debugging, or high-risk edits.'
    ]
  };
}

function eventEvidence(event: StoredEvent, detail: string): string {
  return `event #${event.id} ${event.createdAt}: ${detail}`;
}

function parseRaw(event: StoredEvent): Record<string, unknown> {
  try {
    const parsed = JSON.parse(event.rawJson) as unknown;
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function isTool(event: StoredEvent, names: string[]): boolean {
  return names.some((name) => event.toolName?.toLowerCase() === name.toLowerCase());
}

function outputLength(event: StoredEvent): number {
  return event.stdoutLength + event.stderrLength + event.resultLength;
}

function sumTokens(events: StoredEvent[]): number {
  return events.reduce((sum, event) => sum + event.estimatedTokens, 0);
}

function normalizeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim();
}

function preview(text: string): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 90 ? `${normalized.slice(0, 87)}...` : normalized;
}

function unique(values: Array<string | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}
