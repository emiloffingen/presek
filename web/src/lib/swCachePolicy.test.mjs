import test from 'node:test';
import assert from 'node:assert/strict';
import {
  shouldCacheApiPath,
  shouldStoreApiResponse,
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
