import test from 'node:test';
import assert from 'node:assert/strict';

import { getCsrfTokenAsync } from './personalization.js';

test('getCsrfTokenAsync prefers the cookie set by /api/csrf-token over the body token', async (t) => {
  const doc = { cookie: '' };
  globalThis.document = doc;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    doc.cookie = 'csrf_token=111:cookie';
    return { ok: true, json: async () => ({ csrf_token: '111:body' }) };
  };
  t.after(() => {
    delete globalThis.document;
    globalThis.fetch = realFetch;
  });

  assert.equal(await getCsrfTokenAsync(), '111:cookie');
});

test('getCsrfTokenAsync falls back to the body token when no cookie was set', async (t) => {
  globalThis.document = { cookie: '' };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ csrf_token: '111:body' }) });
  t.after(() => {
    delete globalThis.document;
    globalThis.fetch = realFetch;
  });

  assert.equal(await getCsrfTokenAsync(), '111:body');
});
