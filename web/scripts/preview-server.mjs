#!/usr/bin/env node
/**
 * Shared helpers for local Astro preview (port 4321).
 * Prevents ERR_MODULE_NOT_FOUND 500s from stale preview processes or broken dist/.
 */

import { spawn, spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webDir = dirname(dirname(fileURLToPath(import.meta.url)));
const appRoot = dirname(webDir);
const DEFAULT_PORT = '4321';
const DEFAULT_HOST = '127.0.0.1';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function freePort(port) {
  const result = spawnSync('fuser', ['-k', `${port}/tcp`], { stdio: 'ignore' });
  if (result.status === 0) {
    return true;
  }
  return false;
}

export function ensureAstroBuild() {
  const script = join(appRoot, 'deploy', 'ensure_astro_build.sh');
  const result = spawnSync('bash', [script], {
    cwd: webDir,
    env: { ...process.env, APP_ROOT: appRoot, WEB_DIR: webDir },
    stdio: 'inherit',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

export async function preparePreviewEnvironment({
  port = DEFAULT_PORT,
  killExisting = true,
} = {}) {
  if (killExisting && freePort(port)) {
    await sleep(500);
  }
  ensureAstroBuild();
}

export async function waitForPreviewUrl(url, attempts = 30) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(url, { redirect: 'follow' });
      if (res.ok || res.status < 500) return;
    } catch {
      // retry
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

export async function startDetachedPreview({
  port = DEFAULT_PORT,
  host = DEFAULT_HOST,
  killExisting = true,
} = {}) {
  await preparePreviewEnvironment({ port, killExisting });

  const child = spawn(
    'npx',
    ['astro', 'preview', '--host', host, '--port', String(port)],
    {
      cwd: webDir,
      stdio: 'ignore',
      detached: true,
    },
  );
  child.unref();

  const url = `http://${host}:${port}/`;
  await waitForPreviewUrl(url);
  return child;
}

export function stopDetachedPreview(child) {
  if (!child?.pid) return;
  try {
    process.kill(-child.pid);
  } catch {
    // ignore
  }
}

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  const port = process.env.PREVIEW_PORT || DEFAULT_PORT;
  preparePreviewEnvironment({ port, killExisting: true }).catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
