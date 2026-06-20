import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { StoredEvent } from '../schemas/events.js';
import { estimateTokens } from '../utils/tokens.js';
import type { BurnProfile, DiagnosisFinding, DiagnosisReport } from './categories.js';
import { aggregateConfidence, calculateFuelScore, fuelRating, savingsRange } from './scoring.js';
import { generalDiagnosis, rankedNextChanges } from './recommendations.js';

export function diagnoseFuel(input: {
  events: StoredEvent[];
  projectRoot: string;
  totalTokens?: number;
  generatedAt?: string;
}): DiagnosisReport {
  const findings = [
    hugeToolOutput(input.events),
    repeatedInstructions(input.events),
    bloatedProjectContext(input.projectRoot),
    broadPrompt(input.events),
    unnecessaryFullFileReads(input.events),
    rereadLoop(input.events),
    multiDeliverablePrompt(input.events),
    lateCompaction(input.events),
    subagentOverkill(input.events),
    styleBoilerplateOverhead(input.events),
    missingAcceptanceCriteria(input.events),
    prematureArchitectureDebate(input.events)
  ].filter((finding): finding is DiagnosisFinding => Boolean(finding))
    .sort((a, b) => b.estimatedWasteTokens - a.estimatedWasteTokens || a.category.localeCompare(b.category));

  const totalTokens = input.totalTokens ?? sum(input.events.map((event) => event.estimatedTokens));
  const suspectedWasteTokens = Math.min(totalTokens, sum(findings.map((finding) => finding.estimatedWasteTokens)));
  const fuelScore = calculateFuelScore(totalTokens, suspectedWasteTokens);
  const burnProfile: BurnProfile = {
    usefulEstimatedTokens: Math.max(0, totalTokens - suspectedWasteTokens),
    suspectedWasteTokens,
    wastePercentage: totalTokens === 0 ? 0 : Math.round((suspectedWasteTokens / totalTokens) * 100),
    topBurnCauses: findings.slice(0, 3).map((finding) => finding.category),
    confidence: aggregateConfidence(findings)
  };

  return {
    generatedAt: input.generatedAt ?? new Date().toISOString(),
    fuelScore,
    fuelRating: fuelRating(fuelScore),
    burnProfile,
    generalDiagnosis: generalDiagnosis(findings),
    findings,
    whatToChangeNext: rankedNextChanges(findings)
  };
}

function hugeToolOutput(events: StoredEvent[]): DiagnosisFinding | null {
  const hits = events.filter((event) => event.stdoutLength + event.stderrLength + event.resultLength > 16000);
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.5);
  return finding('Huge Tool Output', 'high', 'high', waste, hits.map((event) => ev(event, `${event.toolName ?? 'tool'} output ${event.stdoutLength + event.stderrLength + event.resultLength} chars`)), 'Large tool output is flooding context. The agent is burning fuel on exhaust instead of signal.', ['Pipe through tail/head/grep.', 'Use concise test reporters.', 'Redirect large logs to files.', 'Inspect focused excerpts.'], 'Add CLAUDE.md rule suggesting output caps.');
}

function repeatedInstructions(events: StoredEvent[]): DiagnosisFinding | null {
  const prompts = events.filter((event) => event.eventType === 'UserPromptSubmit' && event.promptText);
  const groups = new Map<string, StoredEvent[]>();
  for (const event of prompts) {
    const key = normalize(event.promptText ?? '');
    if (key.length < 80) continue;
    groups.set(key, [...(groups.get(key) ?? []), event]);
  }
  const hits = [...groups.values()].filter((group) => group.length > 1).flat();
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.45);
  return finding('Repeated Instructions', 'medium', 'high', waste, hits.map((event) => ev(event, 'repeated prompt block')), 'The engine is idling on the same instructions. Store durable rules once instead of re-sending them.', ['Move stable rules into CLAUDE.md.', 'Move procedural instructions into .claude/skills.', 'Create slash commands for repeated workflows.'], 'Create slash command or skill proposal.');
}

function bloatedProjectContext(projectRoot: string): DiagnosisFinding | null {
  const files = ['CLAUDE.md', '.claude/skills/token-efficient-project/SKILL.md']
    .map((file) => join(projectRoot, file))
    .filter(existsSync);
  const hits = files.map((file) => ({ file, tokens: estimateTokens(readFileSync(file, 'utf8')) })).filter((item) => item.tokens > 2000);
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((hit) => hit.tokens)) * 0.45);
  return finding('Bloated Project Context', 'medium', 'medium', waste, hits.map((hit) => `${hit.file}: ${hit.tokens.toLocaleString()} estimated tokens`), 'The project is carrying heavy context weight. Permanent rules should be short and load-bearing.', ['Shorten CLAUDE.md.', 'Split long procedures into skills.', 'Use progressive disclosure.', 'Keep CLAUDE.md to permanent operating rules only.'], 'Shorter CLAUDE.md proposal.');
}

function broadPrompt(events: StoredEvent[]): DiagnosisFinding | null {
  const vague = /\b(improve|optimize|review|analyze|fix everything|make better|brainstorm)\b/i;
  const hits = events.filter((event) => event.promptText && vague.test(event.promptText) && !hasPath(event.promptText) && !hasAcceptance(event.promptText));
  if (!hits.length) return null;
  const waste = Math.max(1, Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.35));
  return finding('Broad Prompt', 'medium', 'medium', waste, hits.map((event) => ev(event, preview(event.promptText ?? ''))), 'The prompt opens the throttle too wide. Without file targets or stop lines, exploration burn rises.', ['Add target files.', 'Add done-when criteria.', 'Specify smallest safe change.', 'Split strategy from implementation.'], 'Prompt template proposal.');
}

function unnecessaryFullFileReads(events: StoredEvent[]): DiagnosisFinding | null {
  const bad = /(package-lock|pnpm-lock|dist\/|build\/|coverage\/|node_modules\/|generated)/;
  const hits = events.filter((event) => (event.toolName === 'Read' || /^(cat|sed)\b/.test(event.command ?? '')) && ((event.resultLength > 12000) || bad.test(event.filePath ?? event.command ?? '')));
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.4);
  return finding('Unnecessary Full File Reads', 'medium', 'high', waste, hits.map((event) => ev(event, event.filePath ?? event.command ?? 'large read')), 'The agent is filling the tank with whole files when a small range would be enough.', ['Search first with rg/grep.', 'Read only relevant ranges.', 'Avoid generated/build/lock files unless specifically needed.']);
}

function rereadLoop(events: StoredEvent[]): DiagnosisFinding | null {
  const reads = events.filter((event) => event.toolName === 'Read' && event.filePath);
  const counts = new Map<string, StoredEvent[]>();
  for (const event of reads) counts.set(event.filePath!, [...(counts.get(event.filePath!) ?? []), event]);
  const hits = [...counts.values()].filter((group) => group.length >= 3).flat();
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.3);
  return finding('Re-read Loop', 'medium', 'medium', waste, hits.slice(0, 8).map((event) => ev(event, `re-read ${event.filePath}`)), 'The agent is reburning context it already had. Re-reads should follow edits or uncertainty.', ['Ask Claude to use prior context.', 'Only re-read changed files.', 'Summarize relevant file state once.']);
}

function multiDeliverablePrompt(events: StoredEvent[]): DiagnosisFinding | null {
  const words = /\b(implement|docs?|tests?|strategy|refactor|roadmap|cleanup|audit|plan)\b/gi;
  const hits = events.filter((event) => event.promptText && ((event.promptText.match(words)?.length ?? 0) >= 4 || /^\s*\d+[.)]/m.test(event.promptText)));
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.25);
  return finding('Multi-Deliverable Prompt', 'low', 'medium', waste, hits.map((event) => ev(event, preview(event.promptText ?? ''))), 'One turn is carrying too much load. Bundled work increases search, planning, and verification burn.', ['Split into sequential tasks.', 'Run implementation first.', 'Run docs/cleanup after tests pass.']);
}

function lateCompaction(events: StoredEvent[]): DiagnosisFinding | null {
  const bySession = new Map<string, StoredEvent[]>();
  for (const event of events) bySession.set(event.sessionId ?? 'unknown', [...(bySession.get(event.sessionId ?? 'unknown') ?? []), event]);
  // (large by tokens OR by turn count) AND not yet compacted. The old expression
  // lacked parens — `a && b || c` flagged ANY session with >=8 Stop events (every
  // long session) regardless of size or whether it had already compacted.
  const hits = [...bySession.values()].filter((group) => {
    const tokens = sum(group.map((event) => event.estimatedTokens));
    const stops = group.filter((event) => event.eventType === 'Stop').length;
    const compacted = group.some((event) => event.eventType.includes('Compact'));
    return (tokens > 40000 || stops >= 8) && !compacted;
  }).flat();
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.2);
  return finding('Late Compaction / Long Session Drift', 'medium', 'medium', waste, hits.slice(0, 4).map((event) => ev(event, 'long session drift')), 'The session is hauling stale load. Old context can cost more than it helps.', ['Compact.', 'Start a fresh session.', 'Export a short state summary.', 'Use /clear or equivalent when switching tasks.']);
}

function subagentOverkill(events: StoredEvent[]): DiagnosisFinding | null {
  const hits = events.filter((event) => /task|subagent|spawn_agent/i.test(`${event.toolName ?? ''} ${event.rawJson}`));
  if (hits.length < 3) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.3);
  return finding('Subagent Overkill', 'medium', 'medium', waste, hits.map((event) => ev(event, event.toolName ?? 'subagent')), 'Parallel agents add fuel cost. Use them when the task size justifies the extra engines.', ['Use one focused agent/pass.', 'Reserve subagents for large investigations.']);
}

function styleBoilerplateOverhead(events: StoredEvent[]): DiagnosisFinding | null {
  const adjectives = /\b(amazing|beautiful|delightful|thoughtful|elegant|world-class|polished|incredible|friendly|motivating|inspiring)\b/gi;
  const hits = events.filter((event) => event.promptText && (event.promptText.match(adjectives)?.length ?? 0) >= 4);
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.2);
  return finding('Style/Boilerplate Overhead', 'low', 'medium', waste, hits.map((event) => ev(event, preview(event.promptText ?? ''))), 'Non-operational wording is adding cabin noise. It burns tokens without steering implementation.', ['Replace with concise operating rules.', 'Store durable style rules once.', 'Use short task-specific instructions.']);
}

function missingAcceptanceCriteria(events: StoredEvent[]): DiagnosisFinding | null {
  const hits = events.filter((event) => event.promptText && !hasAcceptance(event.promptText));
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.2);
  return finding('Missing Acceptance Criteria', 'low', 'medium', waste, hits.slice(0, 8).map((event) => ev(event, preview(event.promptText ?? ''))), 'There is no stop line. Without a finish condition, the agent may keep searching or polishing.', ['Add done-when criteria.', 'Provide exact test command.', 'Define expected output.'], '/task command template.');
}

function prematureArchitectureDebate(events: StoredEvent[]): DiagnosisFinding | null {
  const hits = events.filter((event) => event.promptText && /\b(compare|choose|which stack|framework|library|architecture|tools)\b/i.test(event.promptText) && /\b(implement|fix|change|repo|existing)\b/i.test(event.promptText));
  if (!hits.length) return null;
  const waste = Math.round(sum(hits.map((event) => event.estimatedTokens)) * 0.25);
  return finding('Premature Architecture Debate', 'low', 'medium', waste, hits.map((event) => ev(event, preview(event.promptText ?? ''))), 'The engine is revving in the garage. Stack debate is consuming fuel when the repo already points to execution.', ['Use existing stack.', 'Make smallest compatible change.', 'Defer architecture discussion to a separate session.']);
}

function finding(category: DiagnosisFinding['category'], severity: DiagnosisFinding['severity'], confidence: DiagnosisFinding['confidence'], waste: number, evidence: string[], whyThisMatters: string, recommendedFixes: string[], patchableAction?: string): DiagnosisFinding {
  return { category, severity, confidence, estimatedWasteTokens: waste, savingsRange: savingsRange(waste), evidence, whyThisMatters, recommendedFixes, patchableAction };
}

function ev(event: StoredEvent, text: string): string {
  return `event #${event.id} ${event.createdAt}: ${text}`;
}
function sum(values: number[]): number { return values.reduce((a, b) => a + b, 0); }
function normalize(text: string): string { return text.toLowerCase().replace(/\s+/g, ' ').trim(); }
function hasPath(text: string): boolean { return /(\b[\w.-]+\.(ts|tsx|js|jsx|py|md|json)\b|\/)/i.test(text); }
function hasAcceptance(text: string): boolean { return /\b(done when|success means|run this command|expected output|test command|pnpm test|npm test|vitest|pytest)\b/i.test(text); }
function preview(text: string): string { const one = text.replace(/\s+/g, ' ').trim(); return one.length > 90 ? `${one.slice(0, 87)}...` : one; }
