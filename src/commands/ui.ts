import { startUiServer } from '../local-ui/server.js';

type UiOptions = {
  port?: string;
  open?: boolean;
  db?: string;
};

export async function runUi(options: UiOptions): Promise<void> {
  const port = Number.parseInt(options.port ?? '4317', 10);

  await startUiServer({
    port: Number.isFinite(port) ? port : 4317,
    open: options.open ?? true,
    db: options.db
  });
}
