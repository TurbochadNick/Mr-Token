import { isFresh, isInsideGracePeriod, readAuthConfig, writeAuthConfig } from './config.js';
import { authReasonMessage } from './commands.js';
import { updateNotice, verifyLicenseKey } from './license.js';

export async function requireActiveLicense(): Promise<boolean> {
  const config = readAuthConfig();
  if (!config) {
    console.error('Not logged in. Run `mrtoken login <key>`.');
    process.exitCode = 1;
    return false;
  }

  if (isFresh(config.verified_at) && config.active !== false) return true;

  try {
    const result = await verifyLicenseKey(config.license_key);
    if (!result.ok || result.active !== true) {
      console.error(authReasonMessage(result.reason));
      process.exitCode = 1;
      return false;
    }

    writeAuthConfig({
      ...config,
      verified_at: Date.now(),
      user_id: result.user_id ?? config.user_id,
      active: true,
      latest_version: result.latest_version ?? config.latest_version
    });

    const notice = updateNotice(result.latest_version);
    if (notice) console.log(notice);
    return true;
  } catch {
    if (!isInsideGracePeriod(config.verified_at)) {
      console.error('Could not verify your Mr Token license. Connect to the internet and run `mrtoken login <key>`.');
      process.exitCode = 1;
      return false;
    }

    return true;
  }
}

export function withLicense<T extends unknown[]>(action: (...args: T) => void | Promise<void>) {
  return async (...args: T): Promise<void> => {
    if (!(await requireActiveLicense())) return;
    await action(...args);
  };
}
