#!/usr/bin/env node
import { readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const clientDir = path.join(root, 'dist', 'client', '_astro');

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await walk(fullPath));
      continue;
    }
    files.push(fullPath);
  }
  return files;
}

async function main() {
  let files;
  try {
    files = await walk(clientDir);
  } catch (error) {
    console.error('Run `npm run build` before `npm run analyze`.');
    console.error(error.message);
    process.exit(1);
  }

  const assets = await Promise.all(files.map(async (file) => {
    const info = await stat(file);
    return {
      file: path.relative(root, file),
      bytes: info.size,
    };
  }));

  assets.sort((left, right) => right.bytes - left.bytes);

  console.log('Top client bundles:');
  for (const asset of assets.slice(0, 25)) {
    const kb = (asset.bytes / 1024).toFixed(1);
    console.log(`${kb.padStart(8)} KB  ${asset.file}`);
  }

  const total = assets.reduce((sum, asset) => sum + asset.bytes, 0);
  console.log(`\nTotal _astro assets: ${(total / 1024 / 1024).toFixed(2)} MB (${assets.length} files)`);
}

main();
