import type { NormalizedHookEvent } from '../../schemas/events.js';
import { estimateTokens, stringifyEventValue } from '../../utils/tokens.js';
import type { ClaudeHookEvent } from './events.js';

export function normalizeHookEvent({
  event,
  hookEvent,
  projectPath,
  timestamp = new Date().toISOString()
}: {
  event: ClaudeHookEvent;
  hookEvent?: string;
  projectPath?: string;
  timestamp?: string;
}): NormalizedHookEvent {
  const toolInput = asRecord(event.tool_input);
  const toolResponse = asRecord(event.tool_response);
  const prompt = firstString(event.prompt, getString(event, 'prompt_text'), getString(event, 'message'));
  const stdout = firstString(getString(event, 'stdout'), getString(toolResponse, 'stdout'));
  const stderr = firstString(getString(event, 'stderr'), getString(toolResponse, 'stderr'));
  const result = firstString(
    getString(event, 'result'),
    getString(event, 'response'),
    getString(toolResponse, 'result'),
    getString(toolResponse, 'content')
  );
  const command = firstString(getString(event, 'command'), getString(toolInput, 'command'));
  const filePath = firstString(
    getString(event, 'file_path'),
    getString(event, 'path'),
    getString(toolInput, 'file_path'),
    getString(toolInput, 'path')
  );
  const eventType = firstString(event.hook_event_name, hookEvent, getString(event, 'event_type')) ?? 'Unknown';
  const resolvedProjectPath = firstString(event.cwd, getString(event, 'project_path'), projectPath) ?? process.cwd();
  const tokenBasis = [prompt, command, stdout, stderr, result].filter(Boolean).join('\n');

  return {
    timestamp,
    projectPath: resolvedProjectPath,
    sessionId: event.session_id ?? null,
    eventType,
    toolName: event.tool_name ?? null,
    filePath: filePath ?? null,
    command: command ?? null,
    promptLength: lengthOf(prompt),
    stdoutLength: lengthOf(stdout),
    stderrLength: lengthOf(stderr),
    resultLength: lengthOf(result),
    estimatedTokens: estimateTokens(tokenBasis || stringifyEventValue(event)),
    rawEvent: event
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function getString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === 'string' ? value : undefined;
}

function firstString(...values: Array<string | null | undefined>): string | undefined {
  return values.find((value) => typeof value === 'string' && value.length > 0) ?? undefined;
}

function lengthOf(value: string | undefined): number {
  return value?.length ?? 0;
}
