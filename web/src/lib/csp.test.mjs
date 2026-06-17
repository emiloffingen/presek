import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFrameAncestorsPolicy, generateCspNonce } from './csp.ts';

test('generateCspNonce returns hex string without dashes', () => {
  const nonce = generateCspNonce();
  assert.match(nonce, /^[a-f0-9]{32}$/);
});

test('buildFrameAncestorsPolicy blocks embedding', () => {
  const policy = buildFrameAncestorsPolicy();
  assert.equal(policy, "frame-ancestors 'none'");
});
