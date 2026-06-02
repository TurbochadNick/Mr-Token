import { handleHookEvent } from '../adapters/claude-code/handler.js';
import { defaultDbPath, defaultEventsPath } from '../utils/paths.js';

type WatchOptions = {
  db?: string;
  events?: string;
  hookEvent?: string;
  stdin?: boolean;
  event?: string;
};

export async function runWatch(options: WatchOptions): Promise<void> {
  const raw = options.stdin ? await readStdin() : options.event;

  if (!raw) {
    console.error('No event JSON provided. Use --stdin or --event.');
    process.exitCode = 1;
    return;
  }

  const dbPath = options.db ?? defaultDbPath();
  const eventsPath = options.events ?? defaultEventsPath();
  const { id } = handleHookEvent({ rawJson: raw, dbPath, eventsPath, hookEvent: options.hookEvent });

  console.log(`Stored event #${id}`);
}

function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
      data += chunk;
    });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}
