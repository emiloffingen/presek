import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

let cachedVersion = '8.2.3';

try {
  // Only execute this in Node.js server environment
  if (typeof process !== 'undefined' && process.versions && process.versions.node) {
    const here = path.dirname(fileURLToPath(import.meta.url));
    // Resolve against the module (stable) before falling back to cwd, so the
    // reported version doesn't depend on where the server was launched from.
    const candidates = [
      path.resolve(here, '../../VERSION'),   // web/src/lib -> repo root
      path.resolve(here, '../../../VERSION'),
      path.join(process.cwd(), '../VERSION'), // web -> repo root
      path.join(process.cwd(), 'VERSION'),
    ];
    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) {
        cachedVersion = fs.readFileSync(candidate, 'utf-8').trim();
        break;
      }
    }
  }
} catch (e) {
  console.warn('Failed to read VERSION file, using default:', e);
}

export const APP_VERSION = cachedVersion;
export const APP_VERSION_LABEL = cachedVersion.endsWith('.0') && cachedVersion.split('.').length === 3
  ? cachedVersion.substring(0, cachedVersion.lastIndexOf('.'))
  : cachedVersion;
