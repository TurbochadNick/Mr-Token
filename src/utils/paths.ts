import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';

// Data-dir resolution — the TypeScript side of the shared contract documented in
// backend/docs/DATA-DIR.md. The Python backend (backend/mrtoken/datadir.py)
// implements the IDENTICAL algorithm. Change BOTH sides together or they drift.

const MARKERS = ['.git', 'package.json', 'pyproject.toml'];

function normalize(path: string): string {
  return resolve(path).replace(/[/\\]+$/, '') || '/';
}

function hasMarker(dir: string): boolean {
  return MARKERS.some((m) => existsSync(join(dir, m)));
}

export function findProjectRoot(startDir = process.cwd()): string {
  let current = normalize(startDir);

  while (true) {
    if (hasMarker(current)) {
      return current;
    }

    const parent = dirname(current);

    if (parent === current) {
      // Not inside any project. Returns the start dir for back-compat callers;
      // defaultDataDir() detects this (no marker) and routes to the central
      // store instead of scattering .token-tithe/ into the cwd.
      return normalize(startDir);
    }

    current = parent;
  }
}

// Stable per-project key. MUST match the Python implementation: basename
// (lowercased, non-alnum -> '-', stripped) + '-' + sha256(absPath)[:8].
export function projectKey(path: string): string {
  const abs = normalize(path);
  const slug = basename(abs).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'root';
  const digest = createHash('sha256').update(abs).digest('hex').slice(0, 8);
  return `${slug}-${digest}`;
}

export function centralDefault(): string {
  const xdg = process.env.XDG_DATA_HOME;
  if (xdg) return join(xdg, 'token-tithe');
  return join(homedir(), '.mrtoken', 'data');
}

export function defaultDataDir(projectRoot = findProjectRoot()): string {
  const dataDirEnv = process.env.MRTOKEN_DATA_DIR;

  if (dataDirEnv) {
    // Full-central opt-in: every project under one home, separated by key.
    return join(dataDirEnv, 'projects', projectKey(projectRoot));
  }
  if (hasMarker(projectRoot)) {
    // Default: per-project (keeps the local-first privacy story).
    return join(projectRoot, '.token-tithe');
  }
  // Non-project fallback: never scatter into cwd -> central default, keyed by it.
  return join(centralDefault(), 'projects', projectKey(projectRoot));
}

export function defaultDbPath(projectRoot = findProjectRoot()): string {
  return process.env.TOKEN_TITHE_DB ?? process.env.MRTOKEN_DB ?? join(defaultDataDir(projectRoot), 'token-tithe.db');
}

export function defaultEventsPath(projectRoot = findProjectRoot()): string {
  return join(defaultDataDir(projectRoot), 'events.jsonl');
}

// Claude settings stay project-local — only the DATA dir moves.
export function defaultClaudeSettingsPath(projectRoot = findProjectRoot()): string {
  return join(projectRoot, '.claude', 'settings.local.json');
}
