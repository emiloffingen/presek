#!/usr/bin/env node
import { existsSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import puppeteer from 'puppeteer-core';

function findChromeInCache(dir) {
  if (!existsSync(dir)) return null;
  try {
    const files = readdirSync(dir);
    for (const file of files) {
      const fullPath = join(dir, file);
      if (statSync(fullPath).isDirectory()) {
        const found = findChromeInCache(fullPath);
        if (found) return found;
      } else if (file === 'chrome' || file === 'chromium') {
        return fullPath;
      }
    }
  } catch (e) {}
  return null;
}

function resolveChromePath() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  
  // Try candidates first
  for (const candidate of [
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ]) {
    if (existsSync(candidate)) return candidate;
  }

  // Try user cache directory
  const homeDir = process.env.HOME || '/home/emiloffingen';
  const cachePath = findChromeInCache(join(homeDir, '.cache', 'puppeteer'));
  if (cachePath) return cachePath;

  return null;
}

async function capture(url, label) {
  const chromePath = resolveChromePath();
  if (!chromePath) {
    console.error('Chrome/Chromium not found. Cannot capture screenshot.');
    process.exit(1);
  }
  console.log(`Using Chrome binary: ${chromePath}`);

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });

  try {
    const page = await browser.newPage();
    
    // Capture Desktop
    await page.setViewport({ width: 1440, height: 900 });
    console.log(`Navigating to ${url} (Desktop)...`);
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
    
    // Wait for header elements to render
    await page.waitForSelector('#main-header', { timeout: 10000 }).catch(() => {});
    
    const screenshotDir = join(process.cwd(), 'screenshots');
    mkdirSync(screenshotDir, { recursive: true });
    
    const desktopPath = join(screenshotDir, `${label}-desktop.png`);
    await page.screenshot({ path: desktopPath, fullPage: false });
    console.log(`Saved desktop screenshot to ${desktopPath}`);

    // Capture Mobile
    await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true });
    console.log(`Navigating to ${url} (Mobile)...`);
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForSelector('#main-header', { timeout: 10000 }).catch(() => {});
    
    const mobilePath = join(screenshotDir, `${label}-mobile.png`);
    await page.screenshot({ path: mobilePath, fullPage: false });
    console.log(`Saved mobile screenshot to ${mobilePath}`);
  } finally {
    await browser.close();
  }
}

async function main() {
  const url = process.argv[2] || 'https://presek.live/';
  const label = process.argv[3] || 'homepage';
  await capture(url, label);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
