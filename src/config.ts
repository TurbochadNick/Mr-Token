import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { z } from 'zod';

const tokenTitheConfigSchema = z
  .object({
    ai: z
      .object({
        enabled: z.boolean().default(false),
        model: z.string().default('claude-haiku-4-5'),
        redaction: z.boolean().default(true),
        fullContext: z.boolean().default(false)
      })
      .default({})
  })
  .default({});

export type TokenTitheConfig = z.infer<typeof tokenTitheConfigSchema>;

export const defaultTokenTitheConfig: TokenTitheConfig = {
  ai: {
    enabled: false,
    model: 'claude-haiku-4-5',
    redaction: true,
    fullContext: false
  }
};

export function loadTokenTitheConfig(projectRoot: string): TokenTitheConfig {
  const packageJsonPath = join(projectRoot, 'package.json');
  if (!existsSync(packageJsonPath)) return defaultTokenTitheConfig;

  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8')) as { tokenTithe?: unknown };
    const parsed = tokenTitheConfigSchema.parse(packageJson.tokenTithe ?? {});

    return {
      ai: {
        ...defaultTokenTitheConfig.ai,
        ...parsed.ai
      }
    };
  } catch {
    return defaultTokenTitheConfig;
  }
}
