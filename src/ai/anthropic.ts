import type { TokenTitheConfig } from '../config.js';
import type { RedactedAuditSummary } from './redacted-summary.js';

export type AiAuditResult =
  | { status: 'disabled'; message: string }
  | { status: 'missing-key'; message: string }
  | { status: 'ok'; message: string }
  | { status: 'error'; message: string };

export async function runAnthropicAudit(input: {
  config: TokenTitheConfig;
  summary: RedactedAuditSummary;
}): Promise<AiAuditResult> {
  if (!input.config.ai.enabled) {
    return { status: 'disabled', message: 'AI review disabled by tokenTithe.ai.enabled=false.' };
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return { status: 'missing-key', message: 'AI review enabled, but ANTHROPIC_API_KEY is not set.' };
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: input.config.ai.model,
        max_tokens: 800,
        messages: [
          {
            role: 'user',
            content: [
              'You are reviewing a token-tithe audit summary.',
              'Do not ask for raw source files or transcripts.',
              'Return concise prioritized recommendations based only on this structured summary.',
              JSON.stringify(input.summary)
            ].join('\n\n')
          }
        ]
      })
    });

    if (!response.ok) {
      return { status: 'error', message: `AI review failed with HTTP ${response.status}.` };
    }

    const json = (await response.json()) as { content?: Array<{ type?: string; text?: string }> };
    const message = json.content?.find((part) => part.type === 'text')?.text?.trim();

    return {
      status: 'ok',
      message: message || 'AI review returned no text.'
    };
  } catch (error) {
    return {
      status: 'error',
      message: error instanceof Error ? error.message : 'AI review failed.'
    };
  }
}
