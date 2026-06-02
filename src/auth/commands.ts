import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { deleteAuthConfig, licenseKeyPattern, maskLicenseKey, readAuthConfig, writeAuthConfig } from './config.js';
import { downloadInstaller, updateNotice, verifyLicenseKey } from './license.js';

export async function runLogin(key: string): Promise<void> {
  if (!licenseKeyPattern.test(key)) {
    console.error('Your key is invalid. Run `mrtoken login <new-key>`.');
    process.exitCode = 1;
    return;
  }

  try {
    const result = await verifyLicenseKey(key);
    if (!result.ok || result.active !== true) {
      console.error(authReasonMessage(result.reason));
      process.exitCode = 1;
      return;
    }

    const verifiedAt = Date.now();
    writeAuthConfig({
      license_key: key,
      verified_at: verifiedAt,
      user_id: result.user_id,
      active: true,
      latest_version: result.latest_version
    });
    console.log('Logged in');
    const notice = updateNotice(result.latest_version);
    if (notice) console.log(notice);
  } catch {
    console.error('Could not verify your license key. Check your connection and try again.');
    process.exitCode = 1;
  }
}

export function runLogout(): void {
  deleteAuthConfig();
  console.log('Logged out');
}

export function runWhoami(): void {
  const config = readAuthConfig();
  if (!config) {
    console.log('Not logged in. Run `mrtoken login <key>`.');
    process.exitCode = 1;
    return;
  }

  console.log(`Key: ${maskLicenseKey(config.license_key)}`);
  console.log(`Last verified: ${new Date(config.verified_at).toISOString()}`);
  console.log(`Active: ${config.active === false ? 'no' : 'yes'}`);
  if (config.user_id) console.log(`User: ${config.user_id}`);
}

export async function runUpdate(): Promise<void> {
  const config = readAuthConfig();
  if (!config) {
    console.error('Not logged in. Run `mrtoken login <key>`.');
    process.exitCode = 1;
    return;
  }

  try {
    const bytes = await downloadInstaller(config.license_key);
    const outputPath = join(process.cwd(), 'mrtoken-latest.tgz');
    writeFileSync(outputPath, bytes);
    console.log(`Downloaded ${outputPath}`);
    console.log('Run `npm install -g ./mrtoken-latest.tgz` to install the update.');
  } catch {
    console.error('Could not download the update. Visit https://mrtoken.lovable.app/account or try again later.');
    process.exitCode = 1;
  }
}

export function authReasonMessage(reason: string | undefined): string {
  if (reason === 'revoked' || reason === 'no_subscription') {
    return 'Your Mr Token subscription is inactive. Visit https://mrtoken.lovable.app/account';
  }
  return 'Your key is invalid. Run `mrtoken login <new-key>`.';
}
