import { z } from 'zod';

export const claudeHookEventSchema = z
  .object({
    session_id: z.string().optional(),
    transcript_path: z.string().optional(),
    cwd: z.string().optional(),
    hook_event_name: z.string().optional(),
    prompt: z.string().optional(),
    tool_name: z.string().optional(),
    tool_input: z.unknown().optional(),
    tool_response: z.unknown().optional()
  })
  .passthrough();

export type ClaudeHookEvent = z.infer<typeof claudeHookEventSchema>;

export type NormalizedHookEvent = {
  timestamp: string;
  projectPath: string;
  sessionId: string | null;
  eventType: string;
  toolName: string | null;
  filePath: string | null;
  command: string | null;
  promptLength: number;
  stdoutLength: number;
  stderrLength: number;
  resultLength: number;
  estimatedTokens: number;
  rawEvent: ClaudeHookEvent;
};

export type StoredEvent = {
  id: number;
  sessionId: string | null;
  eventType: string;
  toolName: string | null;
  filePath: string | null;
  command: string | null;
  promptText: string | null;
  promptLength: number;
  stdoutLength: number;
  stderrLength: number;
  resultLength: number;
  estimatedTokens: number;
  projectPath: string | null;
  transcriptPath: string | null;
  rawJson: string;
  createdAt: string;
};
