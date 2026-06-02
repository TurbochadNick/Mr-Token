import { existsSync, mkdtempSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { deleteAuthConfig, maskLicenseKey, readAuthConfig, writeAuthConfig } from '../src/auth/config.js';
import { requireActiveLicense } from '../src/auth/heartbeat.js';
import { downloadInstaller, updateNotice, userAgent, verifyLicenseKey } from '../src/auth/license.js';

describe('Mr Token auth', () => {
  const originalFetch = globalThis.fetch;
  const originalExitCode = process.exitCode;
  const originalConfigPath = process.env.MRTOKEN_CONFIG_PATH;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    process.exitCode = originalExitCode;
    if (originalConfigPath === undefined) {
      delete process.env.MRTOKEN_CONFIG_PATH;
    } else {
      process.env.MRTOKEN_CONFIG_PATH = originalConfigPath;
    }
    vi.restoreAllMocks();
  });

  it('writes config with masked key support and private permissions', () => {
    const configPath = join(mkdtempSync(join(tmpdir(), 'mrtoken-auth-')), 'config.json');
    writeAuthConfig({ license_key: 'mt_ABCD-EFGH-IJKL-WXYZ', verified_at: 123, active: true }, configPath);

    expect(readAuthConfig(configPath)?.license_key).toBe('mt_ABCD-EFGH-IJKL-WXYZ');
    expect(maskLicenseKey('mt_ABCD-EFGH-IJKL-WXYZ')).toBe('mt_ABCD…WXYZ');
    expect((statSync(configPath).mode & 0o777).toString(8)).toBe('600');
  });

  it('verifies licenses with the required user agent', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, user_id: 'user_1', active: true })));

    await expect(verifyLicenseKey('mt_ABCD-EFGH-IJKL-WXYZ', fetchMock as typeof fetch)).resolves.toMatchObject({
      ok: true,
      user_id: 'user_1',
      active: true
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://mrtoken.lovable.app/api/public/license/verify',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'user-agent': userAgent()
        }),
        body: JSON.stringify({ key: 'mt_ABCD-EFGH-IJKL-WXYZ' })
      })
    );
  });

  it('uses cached verification inside the six-hour window', async () => {
    const configPath = join(mkdtempSync(join(tmpdir(), 'mrtoken-auth-')), 'config.json');
    process.env.MRTOKEN_CONFIG_PATH = configPath;
    writeAuthConfig({ license_key: 'mt_ABCD-EFGH-IJKL-WXYZ', verified_at: Date.now(), active: true }, configPath);
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as typeof fetch;

    await expect(requireActiveLicense()).resolves.toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fails closed when the subscription is inactive', async () => {
    const configPath = join(mkdtempSync(join(tmpdir(), 'mrtoken-auth-')), 'config.json');
    process.env.MRTOKEN_CONFIG_PATH = configPath;
    writeAuthConfig({ license_key: 'mt_ABCD-EFGH-IJKL-WXYZ', verified_at: 0, active: true }, configPath);
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: false, active: false, reason: 'revoked' }))) as typeof fetch;
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    await expect(requireActiveLicense()).resolves.toBe(false);
    expect(errorSpy).toHaveBeenCalledWith('Your Mr Token subscription is inactive. Visit https://mrtoken.lovable.app/account');
    expect(process.exitCode).toBe(1);
  });

  it('allows temporary offline use inside the seven-day grace period', async () => {
    const configPath = join(mkdtempSync(join(tmpdir(), 'mrtoken-auth-')), 'config.json');
    process.env.MRTOKEN_CONFIG_PATH = configPath;
    writeAuthConfig({
      license_key: 'mt_ABCD-EFGH-IJKL-WXYZ',
      verified_at: Date.now() - 25 * 60 * 60 * 1000,
      active: true
    }, configPath);
    globalThis.fetch = vi.fn(async () => {
      throw new Error('offline');
    }) as typeof fetch;

    await expect(requireActiveLicense()).resolves.toBe(true);
  });

  it('deletes auth config on logout-compatible removal', () => {
    const configPath = join(mkdtempSync(join(tmpdir(), 'mrtoken-auth-')), 'config.json');
    writeAuthConfig({ license_key: 'mt_ABCD-EFGH-IJKL-WXYZ', verified_at: 123, active: true }, configPath);

    expect(existsSync(configPath)).toBe(true);
    deleteAuthConfig(configPath);
    expect(existsSync(configPath)).toBe(false);
  });

  it('formats update notices when the server reports a newer version', () => {
    expect(updateNotice('0.2.0', '0.1.0')).toBe('Update available: v0.2.0 — run `mrtoken update`');
    expect(updateNotice('0.1.0', '0.1.0')).toBeNull();
  });

  it('downloads the gated installer with the required user agent', async () => {
    const bytes = new Uint8Array([1, 2, 3]);
    const fetchMock = vi.fn(async () => new Response(bytes));

    await expect(downloadInstaller('mt_ABCD-EFGH-IJKL-WXYZ', fetchMock as typeof fetch)).resolves.toEqual(bytes);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://mrtoken.lovable.app/api/public/download?key=mt_ABCD-EFGH-IJKL-WXYZ',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          'user-agent': userAgent()
        })
      })
    );
  });
});
