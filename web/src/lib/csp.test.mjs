import test from 'node:test';
import assert from 'node:assert/strict';
import { buildContentSecurityPolicy, generateCspNonce } from './csp.ts';

test('generateCspNonce returns hex string without dashes', () => {
  const nonce = generateCspNonce();
  assert.match(nonce, /^[a-f0-9]{32}$/);
});

test('buildContentSecurityPolicy uses script nonces without unsafe-inline scripts', () => {
  const policy = buildContentSecurityPolicy('abc123');
  assert.match(policy, /script-src 'self' 'nonce-abc123' https:\/\/www\.googletagmanager\.com/);
  assert.doesNotMatch(policy, /script-src[^;]*unsafe-inline/);
});
