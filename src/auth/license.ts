import { platform } from 'node:os';
import { z } from 'zod';
import { CLI_VERSION } from '../version.js';

export const licenseBaseUrl = 'https://mrtoken.lovable.app';

const verifyResponseSchema = z.object({
  ok: z.boolean(),
  user_id: z.string().optional(),
  active: z.boolean().optional(),
  reason: z.enum(['invalid', 'revoked', 'no_subscription']).optional(),
  latest_version: z.string().optional()
});

export type LicenseVerifyResponse = z.infer<typeof verifyResponseSchema>;

export type FetchLike = typeof fetch;

export async function verifyLicenseKey(key: string, fetchImpl: FetchLike = fetch): Promise<LicenseVerifyResponse> {
  const response = await fetchImpl(`${licenseBaseUrl}/api/public/license/verify`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'user-agent': userAgent()
    },
    body: JSON.stringify({ key })
  });

  const body = await response.json();
  return verifyResponseSchema.parse(body);
}

export async function downloadInstaller(key: string, fetchImpl: FetchLike = fetch): Promise<Uint8Array> {
  const response = await fetchImpl(`${licenseBaseUrl}/api/public/download?key=${encodeURIComponent(key)}`, {
    method: 'GET',
    headers: {
      'user-agent': userAgent()
    }
  });
  if (!response.ok) throw new Error(`download failed: ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

export function userAgent(): string {
  return `mrtoken-cli/${CLI_VERSION} ${platform()}`;
}

export function updateNotice(latestVersion: string | undefined, localVersion = CLI_VERSION): string | null {
  if (!latestVersion) return null;
  if (!isNewerVersion(latestVersion, localVersion)) return null;
  return `Update available: ${formatVersion(latestVersion)} — run \`mrtoken update\``;
}

function isNewerVersion(latestVersion: string, localVersion: string): boolean {
  const latest = parseVersion(latestVersion);
  const local = parseVersion(localVersion);
  for (let index = 0; index < Math.max(latest.length, local.length); index += 1) {
    const left = latest[index] ?? 0;
    const right = local[index] ?? 0;
    if (left > right) return true;
    if (left < right) return false;
  }
  return false;
}

function parseVersion(version: string): number[] {
  return version.replace(/^v/i, '').split(/[.-]/).map((part) => Number.parseInt(part, 10) || 0);
}

function formatVersion(version: string): string {
  return version.startsWith('v') ? version : `v${version}`;
}
