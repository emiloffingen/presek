#!/usr/bin/env node
/**
 * Homepage performance audit via Lighthouse.
 * Usage:
 *   node scripts/lighthouse-homepage.mjs https://presek.live/
 *   node scripts/lighthouse-homepage.mjs --preview   # build preview on :4321
 *   node scripts/lighthouse-homepage.mjs ./report.json
 */

import { spawn } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startDetachedPreview, stopDetachedPreview } from './preview-server.mjs';

const THRESHOLDS = {
  performance: 0.72,
  lcpMs: 4200,
  cls: 0.12,
};

const args = process.argv.slice(2);
const usePreview = args.includes('--preview');
const enforce = args.includes('--enforce');
const pathFlagIndex = args.indexOf('--path');
const labelFlagIndex = args.indexOf('--label');
const previewPath = pathFlagIndex >= 0 ? args[pathFlagIndex + 1] || '/' : '/';
const reportLabel = labelFlagIndex >= 0 ? args[labelFlagIndex + 1] || '' : '';
const filteredArgs = args.filter(
  (a, index) =>
    a !== '--preview'
    && a !== '--enforce'
    && a !== '--path'
    && a !== '--label'
    && (pathFlagIndex < 0 || index !== pathFlagIndex + 1)
    && (labelFlagIndex < 0 || index !== labelFlagIndex + 1),
);

function run(command, commandArgs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: 'inherit', shell: false, ...options });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with code ${code}`));
    });
  });
}

async function startPreview() {
  return startDetachedPreview();
}

function resolveChromePath() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  for (const candidate of [
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

async function runLighthouse(url, outFile) {
  const chromePath = resolveChromePath();
  if (!chromePath) {
    console.warn('Chrome/Chromium not found (set CHROME_PATH). Skipping Lighthouse audit.');
    return 'skipped';
  }

  process.env.CHROME_PATH = chromePath;
  await run('npx', [
    'lighthouse',
    url,
    '--only-categories=performance',
    '--output=json',
    `--output-path=${outFile}`,
    '--chrome-flags=--headless --no-sandbox --disable-gpu',
    '--quiet',
  ]);
}

function summarize(reportPath) {
  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  const perf = report.categories?.performance?.score ?? 0;
  const audits = report.audits || {};
  const lcp = audits['largest-contentful-paint']?.numericValue ?? null;
  const cls = audits['cumulative-layout-shift']?.numericValue ?? null;
  const inp = audits['interaction-to-next-paint']?.numericValue
    ?? audits['experimental-interaction-to-next-paint']?.numericValue
    ?? null;

  const lines = [
    'Lighthouse homepage summary',
    `  Performance score: ${(perf * 100).toFixed(0)}`,
    lcp != null ? `  LCP: ${Math.round(lcp)} ms` : null,
    cls != null ? `  CLS: ${cls.toFixed(3)}` : null,
    inp != null ? `  INP: ${Math.round(inp)} ms` : null,
  ].filter(Boolean);

  console.log(lines.join('\n'));

  const warnings = [];
  if (perf < THRESHOLDS.performance) warnings.push(`performance score below ${THRESHOLDS.performance * 100}`);
  if (lcp != null && lcp > THRESHOLDS.lcpMs) warnings.push(`LCP above ${THRESHOLDS.lcpMs}ms`);
  if (cls != null && cls > THRESHOLDS.cls) warnings.push(`CLS above ${THRESHOLDS.cls}`);

  if (warnings.length) {
    const message = 'Perf budget warnings:\n - ' + warnings.join('\n - ');
    if (enforce) {
      console.error(message);
      return 1;
    }
    console.warn(message);
    return 0;
  }

  return 0;
}

function reportFilename(label = '') {
  if (!label) return 'lighthouse-homepage.json';
  return `lighthouse-homepage-${label}.json`;
}

async function main() {
  let reportPath = filteredArgs[0];
  let previewProc = null;

  try {
    if (usePreview) {
      console.log('Starting astro preview...');
      previewProc = await startPreview();
      const tmp = mkdtempSync(join(tmpdir(), 'presek-lh-'));
      reportPath = join(tmp, 'homepage.json');
      const previewUrl = new URL(previewPath, 'http://127.0.0.1:4321').toString();
      console.log(`Running Lighthouse against preview ${previewUrl}`);
      const result = await runLighthouse(previewUrl, reportPath);
      if (result === 'skipped') {
        process.exitCode = enforce ? 1 : 0;
        return;
      }
      const savedReport = join(process.cwd(), reportFilename(reportLabel));
      writeFileSync(savedReport, readFileSync(reportPath));
      console.log(`Saved ${savedReport}`);
    } else if (!reportPath || reportPath.startsWith('http')) {
      const url = reportPath || 'https://presek.live/';
      const tmp = mkdtempSync(join(tmpdir(), 'presek-lh-'));
      reportPath = join(tmp, 'homepage.json');
      console.log(`Running Lighthouse against ${url}`);
      const result = await runLighthouse(url, reportPath);
      if (result === 'skipped') {
        process.exitCode = enforce ? 1 : 0;
        return;
      }
      const savedReport = join(process.cwd(), reportFilename(reportLabel));
      writeFileSync(savedReport, readFileSync(reportPath));
      console.log(`Saved ${savedReport}`);
    }

    if (!reportPath?.endsWith('.json')) {
      throw new Error('Provide a JSON report path, URL, or --preview');
    }

    process.exitCode = summarize(reportPath);
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  } finally {
    stopDetachedPreview(previewProc);
  }
}

main();
