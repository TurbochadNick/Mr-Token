import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { createReadStream, existsSync } from 'node:fs';
import { join, normalize, relative } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  exportMarkdownReport,
  getLatestDoctorPatch,
  getUiDiagnosis,
  getSetupStatus,
  getUiData,
  getUiEvents,
  getUiFindings,
  getUiSummary,
  runUiDoctor,
  runUiInit
} from './api.js';
import { defaultDbPath, findProjectRoot } from '../utils/paths.js';

export type UiServerOptions = {
  port: number;
  open: boolean;
  db?: string;
};

export async function startUiServer(options: UiServerOptions): Promise<void> {
  const projectRoot = findProjectRoot();
  const dbPath = options.db ?? defaultDbPath(projectRoot);
  assertInsideProject(projectRoot, dbPath);
  const staticRoot = resolveStaticRoot();
  const server = createServer((request, response) => {
    void handleRequest({ request, response, projectRoot, dbPath, staticRoot });
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(options.port, '127.0.0.1', () => resolve());
  });

  const url = `http://localhost:${options.port}`;
  console.log(`Mr Token is running at ${url}`);
  console.log('Local only: bound to 127.0.0.1. No telemetry, upload, or cloud backend.');

  if (options.open) {
    openBrowser(url);
  }
}

async function handleRequest({
  request,
  response,
  projectRoot,
  dbPath,
  staticRoot
}: {
  request: IncomingMessage;
  response: ServerResponse;
  projectRoot: string;
  dbPath: string;
  staticRoot: string;
}): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://localhost');

  try {
    if (url.pathname === '/api/init') {
      requireMethod(request, 'POST');
      sendJson(response, { ok: true, result: runUiInit(projectRoot, dbPath), setup: getSetupStatus(projectRoot, dbPath) });
      return;
    }

    if (url.pathname === '/api/audit/run') {
      requireMethod(request, 'POST');
      sendJson(response, { ok: true, data: getUiData(projectRoot, dbPath) });
      return;
    }

    if (url.pathname === '/api/doctor/run') {
      requireMethod(request, 'POST');
      sendJson(response, { ok: true, result: runUiDoctor(projectRoot, dbPath) });
      return;
    }

    if (url.pathname === '/api/export/report.md') {
      requireMethod(request, 'GET');
      sendMarkdown(response, exportMarkdownReport(projectRoot, dbPath), 'mr-token-report.md');
      return;
    }
  } catch (error) {
    sendError(response, error);
    return;
  }

  if (url.pathname === '/api/summary') {
    sendJson(response, getUiSummary(projectRoot, dbPath));
    return;
  }

  if (url.pathname === '/api/findings') {
    sendJson(response, getUiFindings(projectRoot, dbPath));
    return;
  }

  if (url.pathname === '/api/events') {
    sendJson(response, getUiEvents(projectRoot, dbPath));
    return;
  }

  if (url.pathname === '/api/doctor/latest') {
    sendJson(response, getLatestDoctorPatch(projectRoot));
    return;
  }

  if (url.pathname === '/api/diagnosis') {
    sendJson(response, getUiDiagnosis(projectRoot, dbPath));
    return;
  }

  if (url.pathname === '/api/setup') {
    sendJson(response, getSetupStatus(projectRoot, dbPath));
    return;
  }

  if (url.pathname === '/api/all') {
    sendJson(response, getUiData(projectRoot, dbPath));
    return;
  }

  serveStatic(response, staticRoot, url.pathname);
}

function sendJson(response: ServerResponse, value: unknown): void {
  response.writeHead(200, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  });
  response.end(JSON.stringify(value));
}

function sendMarkdown(response: ServerResponse, value: string, filename: string): void {
  response.writeHead(200, {
    'content-type': 'text/markdown; charset=utf-8',
    'content-disposition': `attachment; filename="${filename}"`,
    'cache-control': 'no-store'
  });
  response.end(value);
}

function sendError(response: ServerResponse, error: unknown): void {
  const message = error instanceof Error ? error.message : 'Request failed.';
  response.writeHead(message === 'Method not allowed' ? 405 : 500, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  });
  response.end(JSON.stringify({ ok: false, error: message }));
}

function requireMethod(request: IncomingMessage, method: string): void {
  if (request.method !== method) {
    throw new Error('Method not allowed');
  }
}

function serveStatic(response: ServerResponse, staticRoot: string, pathname: string): void {
  const requested = pathname === '/' ? '/index.html' : pathname;
  const filePath = normalize(join(staticRoot, requested));
  const safePath = filePath.startsWith(staticRoot) && existsSync(filePath) ? filePath : join(staticRoot, 'index.html');

  if (!existsSync(safePath)) {
    response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    response.end('Mr Token UI has not been built. Run pnpm build first.');
    return;
  }

  response.writeHead(200, { 'content-type': contentType(safePath) });
  createReadStream(safePath).pipe(response);
}

function resolveStaticRoot(): string {
  const currentFile = fileURLToPath(import.meta.url);
  return join(currentFile, '..', '..', 'ui');
}

function contentType(path: string): string {
  if (path.endsWith('.html')) return 'text/html; charset=utf-8';
  if (path.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (path.endsWith('.css')) return 'text/css; charset=utf-8';
  if (path.endsWith('.svg')) return 'image/svg+xml';
  return 'application/octet-stream';
}

function openBrowser(url: string): void {
  const command =
    process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'cmd' : 'xdg-open';
  const args = process.platform === 'win32' ? ['/c', 'start', '', url] : [url];
  const child = spawn(command, args, { detached: true, stdio: 'ignore' });
  child.unref();
}

function assertInsideProject(projectRoot: string, path: string): void {
  const rel = relative(projectRoot, path);
  if (rel.startsWith('..') || rel === '..') {
    throw new Error('Mr Token UI refuses to access a database outside the current project root.');
  }
}
