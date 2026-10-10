#!/usr/bin/env node
import { readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const clientDir = path.join(root, 'dist', 'client', '_astro');

const TOTAL_BUDGET_BYTES = Number(process.env.BUNDLE_BUDGET_TOTAL_BYTES || 1_850_000);
const CLIENT_JS_BUDGET_BYTES = Number(process.env.BUNDLE_BUDGET_CLIENT_JS_BYTES || 190_000);

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
  const enforce = process.argv.includes('--enforce');

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
      name: path.basename(file),
    };
  }));

  assets.sort((left, right) => right.bytes - left.bytes);

  console.log('Top client bundles:');
  for (const asset of assets.slice(0, 25)) {
    const kb = (asset.bytes / 1024).toFixed(1);
    console.log(`${kb.padStart(8)} KB  ${asset.file}`);
  }

  const total = assets.reduce((sum, asset) => sum + asset.bytes, 0);
  const clientJs = assets.find((asset) => asset.name.startsWith('client.') && asset.name.endsWith('.js'));
  console.log(`\nTotal _astro assets: ${(total / 1024 / 1024).toFixed(2)} MB (${assets.length} files)`);

  if (!enforce) {
    return;
  }

  const violations = [];
  if (total > TOTAL_BUDGET_BYTES) {
    violations.push(`total bundle ${total} bytes exceeds budget ${TOTAL_BUDGET_BYTES}`);
  }
  if (clientJs && clientJs.bytes > CLIENT_JS_BUDGET_BYTES) {
    violations.push(`client.js ${clientJs.bytes} bytes exceeds budget ${CLIENT_JS_BUDGET_BYTES}`);
  }

  if (violations.length > 0) {
    console.error('\nBundle budget violations:');
    for (const violation of violations) {
      console.error(`- ${violation}`);
    }
    process.exit(1);
  }

  console.log('\nBundle budgets OK.');
}

main();
