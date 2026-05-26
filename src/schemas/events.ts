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
  rawEvent: Record<string, unknown>;
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
