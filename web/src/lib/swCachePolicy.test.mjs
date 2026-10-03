import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  shouldCacheApiPath,
  shouldStoreApiResponse,
  offlinePageForPath,
} from '../../public/sw-cache-policy.js';

test('shouldCacheApiPath allows public read feeds', () => {
  assert.equal(shouldCacheApiPath('/api/home'), true);
  assert.equal(shouldCacheApiPath('/api/news?lang=mk'), true);
  assert.equal(shouldCacheApiPath('/api/cluster/abc-123'), true);
  assert.equal(shouldCacheApiPath('/api/v1/archive'), true);
});

test('shouldCacheApiPath blocks profile and ops endpoints', () => {
  assert.equal(shouldCacheApiPath('/api/profile/sync'), false);
  assert.equal(shouldCacheApiPath('/api/profile/delivery'), false);
  assert.equal(shouldCacheApiPath('/api/admin/status'), false);
  assert.equal(shouldCacheApiPath('/api/csrf-token'), false);
  assert.equal(shouldCacheApiPath('/api/health'), false);
  assert.equal(shouldCacheApiPath('/api/intelligence/cluster/1/research'), false);
});

test('shouldStoreApiResponse respects private cache directives', () => {
  assert.equal(
    shouldStoreApiResponse(new Response('ok', { status: 200, headers: { 'cache-control': 'private' } })),
    false,
  );
  assert.equal(
    shouldStoreApiResponse(new Response('ok', { status: 200, headers: { 'cache-control': 'no-store' } })),
    false,
  );
  assert.equal(shouldStoreApiResponse(new Response('ok', { status: 200 })), true);
});

test('offlinePageForPath picks the locale-aware fallback', () => {
  assert.equal(offlinePageForPath('/'), '/offline');
  assert.equal(offlinePageForPath('/cluster/abc'), '/offline');
  assert.equal(offlinePageForPath('/mk'), '/mk/offline');
  assert.equal(offlinePageForPath('/mk/'), '/mk/offline');
  assert.equal(offlinePageForPath('/mk/cluster/abc'), '/mk/offline');
  assert.equal(offlinePageForPath(undefined), '/offline');
  assert.equal(offlinePageForPath(''), '/offline');
});

test('sw.js precaches the offline fallbacks and uses the shared policy', () => {
  const sw = readFileSync(
    fileURLToPath(new URL('../../public/sw.js', import.meta.url)),
    'utf8',
  );
  assert.match(sw, /offlinePageForPath/, 'sw.js should reuse the shared offline policy');
  assert.match(sw, /'\/offline'/, 'sw.js should precache /offline');
  assert.match(sw, /'\/mk\/offline'/, 'sw.js should precache /mk/offline');
  assert.match(sw, /navigationPreload/, 'sw.js should enable navigation preload');
  const version = sw.match(/const CACHE_NAME = 'presek-v(\d+)'/);
  assert.ok(version, 'sw.js should declare a versioned CACHE_NAME');
  assert.ok(Number(version[1]) >= 31, 'CACHE_NAME should be bumped to invalidate old caches');
});
