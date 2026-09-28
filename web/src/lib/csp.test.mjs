import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCspPolicy, buildFrameAncestorsPolicy, generateCspNonce } from './csp.ts';

test('generateCspNonce returns hex string without dashes', () => {
  const nonce = generateCspNonce();
  assert.match(nonce, /^[a-f0-9]{32}$/);
});

test('buildFrameAncestorsPolicy blocks embedding', () => {
  const policy = buildFrameAncestorsPolicy();
  assert.equal(policy, "frame-ancestors 'none'");
});

test('buildCspPolicy allows inline style attributes so islands can hydrate', () => {
  const policy = buildCspPolicy('abc123', { scripts: ["'sha256-xyz'"], styles: ["'sha256-style'"] });
  const styleSrc = policy.match(/style-src ([^;]+);/)?.[1] || '';
  // Astro's island runtime / React set inline `style` attributes, which nonces
  // and hashes cannot cover (browsers ignore 'unsafe-inline' as soon as a nonce
  // or hash is present). Without plain 'unsafe-inline' here, hydration silently
  // aborts and every island becomes inert (e.g. the search bar does nothing).
  assert.ok(
    styleSrc.includes("'unsafe-inline'"),
    `style-src must allow inline styles, got: ${styleSrc}`,
  );
  assert.ok(!styleSrc.includes('nonce-'), `style-src must not contain a nonce, got: ${styleSrc}`);
  assert.ok(!styleSrc.includes('sha256-'), `style-src must not contain a hash, got: ${styleSrc}`);
});

test('buildCspPolicy keeps script-src locked to nonce and hashes only', () => {
  const policy = buildCspPolicy('abc123', { scripts: ["'sha256-xyz'"], styles: [] });
  const scriptSrc = policy.match(/script-src ([^;]+);/)?.[1] || '';
  assert.ok(scriptSrc.includes("'nonce-abc123'"));
  assert.ok(scriptSrc.includes("'sha256-xyz'"));
  assert.ok(!scriptSrc.includes("'unsafe-inline'"));
});
