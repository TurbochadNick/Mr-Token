import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { z } from 'zod';

export const sixHoursMs = 6 * 60 * 60 * 1000;
export const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

export const licenseKeyPattern = /^mt_[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$/;

const authConfigSchema = z.object({
  license_key: z.string(),
  verified_at: z.number(),
  user_id: z.string().optional(),
  active: z.boolean().optional(),
  latest_version: z.string().optional()
});

export type AuthConfig = z.infer<typeof authConfigSchema>;

export function getAuthConfigPath(): string {
  return process.env.MRTOKEN_CONFIG_PATH ?? join(homedir(), '.mrtoken', 'config.json');
}

export function readAuthConfig(configPath = getAuthConfigPath()): AuthConfig | null {
  if (!existsSync(configPath)) return null;
  try {
    return authConfigSchema.parse(JSON.parse(readFileSync(configPath, 'utf8')));
  } catch {
    return null;
  }
}

export function writeAuthConfig(config: AuthConfig, configPath = getAuthConfigPath()): void {
  mkdirSync(dirname(configPath), { recursive: true, mode: 0o700 });
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 });
  chmodSync(configPath, 0o600);
}

export function deleteAuthConfig(configPath = getAuthConfigPath()): void {
  if (existsSync(configPath)) rmSync(configPath);
}

export function maskLicenseKey(key: string): string {
  if (key.length <= 12) return 'mt_…';
  return `${key.slice(0, 7)}…${key.slice(-4)}`;
}

export function isFresh(timestamp: number, now = Date.now(), ttlMs = sixHoursMs): boolean {
  return now - timestamp <= ttlMs;
}

export function isInsideGracePeriod(timestamp: number, now = Date.now()): boolean {
  return now - timestamp <= sevenDaysMs;
}
