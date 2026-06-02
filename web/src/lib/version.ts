import fs from 'node:fs';
import path from 'node:path';

let cachedVersion = '6.2.0';

try {
  // Only execute this in Node.js server environment
  if (typeof process !== 'undefined' && process.versions && process.versions.node) {
    const rootPath = process.cwd();
    // VERSION file is located at root, which is one level up from the web directory
    const versionPath = path.join(rootPath, '../VERSION');
    if (fs.existsSync(versionPath)) {
      cachedVersion = fs.readFileSync(versionPath, 'utf-8').trim();
    } else {
      // Try current directory as well just in case
      const localVersionPath = path.join(rootPath, 'VERSION');
      if (fs.existsSync(localVersionPath)) {
        cachedVersion = fs.readFileSync(localVersionPath, 'utf-8').trim();
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
