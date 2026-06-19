import test from 'node:test';
import assert from 'node:assert/strict';
import { safeJsonForScript } from './safeJson.ts';

test('safeJsonForScript escapes script-breaking characters', () => {
  const payload = { title: '</script><script>alert(1)</script>', amp: 'a&b' };
  const encoded = safeJsonForScript(payload);
  assert.ok(!encoded.includes('</script>'));
  assert.ok(encoded.includes('\\u003c/script\\u003e'));
  assert.ok(encoded.includes('\\u0026'));
});
