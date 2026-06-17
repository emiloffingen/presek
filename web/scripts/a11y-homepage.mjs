#!/usr/bin/env node
/**
 * Homepage accessibility audit via axe-core.
 * Usage:
 *   node scripts/a11y-homepage.mjs --preview --enforce
 *   node scripts/a11y-homepage.mjs --preview --enforce --path /mk/ --label mk
 */

import { spawn } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import puppeteer from 'puppeteer-core';
import { AxePuppeteer } from '@axe-core/puppeteer';

const FAIL_IMPACTS = new Set(['critical', 'serious']);

const args = process.argv.slice(2);
const usePreview = args.includes('--preview');
const enforce = args.includes('--enforce');
const pathFlagIndex = args.indexOf('--path');
const labelFlagIndex = args.indexOf('--label');
const pagePath = pathFlagIndex >= 0 ? args[pathFlagIndex + 1] || '/' : '/';
const reportLabel = labelFlagIndex >= 0 ? args[labelFlagIndex + 1] || '' : '';

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForUrl(url, attempts = 30) {
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

async function startPreview() {
  const child = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4321'], {
    cwd: process.cwd(),
    stdio: 'ignore',
    detached: true,
  });
  child.unref();
  await waitForUrl('http://127.0.0.1:4321/');
  return child;
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

function reportFilename(label = '') {
  if (!label) return 'axe-homepage.json';
  return `axe-homepage-${label}.json`;
}

function summarizeViolations(results) {
  const violations = (results.violations || []).filter((v) => FAIL_IMPACTS.has(v.impact));
  const lines = [
    'axe accessibility summary',
    `  URL: ${results.url}`,
    `  Violations (critical/serious): ${violations.length}`,
  ];

  for (const violation of violations) {
    lines.push(`  - [${violation.impact}] ${violation.id}: ${violation.help}`);
    for (const node of violation.nodes.slice(0, 3)) {
      lines.push(`      ${node.target.join(' ')}`);
    }
    if (violation.nodes.length > 3) {
      lines.push(`      …and ${violation.nodes.length - 3} more nodes`);
    }
  }

  console.log(lines.join('\n'));
  return violations;
}

async function runAxe(url, outFile) {
  const chromePath = resolveChromePath();
  if (!chromePath) {
    console.warn('Chrome/Chromium not found (set CHROME_PATH). Skipping axe audit.');
    return 'skipped';
  }

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });

  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'networkidle0', timeout: 60000 });
    const results = await new AxePuppeteer(page).analyze();
    results.url = url;
    writeFileSync(outFile, JSON.stringify(results, null, 2));
    return results;
  } finally {
    await browser.close();
  }
}

async function main() {
  let previewProc = null;
  let exitCode = 0;

  try {
    if (!usePreview) {
      throw new Error('Provide --preview (local URL audits are not supported yet)');
    }

    console.log('Starting astro preview...');
    previewProc = await startPreview();
    const tmp = mkdtempSync(join(tmpdir(), 'presek-axe-'));
    const reportPath = join(tmp, 'homepage.json');
    const previewUrl = new URL(pagePath, 'http://127.0.0.1:4321').toString();
    console.log(`Running axe against preview ${previewUrl}`);

    const results = await runAxe(previewUrl, reportPath);
    if (results === 'skipped') {
      process.exitCode = enforce ? 1 : 0;
      return;
    }

    const savedReport = join(process.cwd(), reportFilename(reportLabel));
    writeFileSync(savedReport, readFileSync(reportPath));
    console.log(`Saved ${savedReport}`);

    const violations = summarizeViolations(results);
    if (violations.length > 0) {
      const message = `${violations.length} critical/serious accessibility violation(s) found`;
      if (enforce) {
        console.error(message);
        exitCode = 1;
      } else {
        console.warn(message);
      }
    }
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    exitCode = 1;
  } finally {
    if (previewProc?.pid) {
      try {
        process.kill(-previewProc.pid);
      } catch {
        // ignore
      }
    }
  }

  process.exitCode = exitCode;
}

main();
