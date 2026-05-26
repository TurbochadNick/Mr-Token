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
