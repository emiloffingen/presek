import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  buildEmbedTrustViewModel,
  buildEmbedClusterUrl,
  resolveEmbedTrustLang,
} from './embedTrustData.ts';

const fixturePath = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../../tests/fixtures/cluster_api_sample.json',
);
const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));

test('resolveEmbedTrustLang prefers explicit lang param', () => {
  assert.equal(resolveEmbedTrustLang('mk', 'presek.live'), 'mk');
  assert.equal(resolveEmbedTrustLang('sr', 'presek.mk'), 'sr');
});

test('resolveEmbedTrustLang falls back to host', () => {
  assert.equal(resolveEmbedTrustLang(null, 'presek.mk'), 'mk');
  assert.equal(resolveEmbedTrustLang(null, 'presek.live'), 'sr');
});

test('buildEmbedClusterUrl is locale-aware', () => {
  assert.equal(buildEmbedClusterUrl('c-1', 'mk'), 'https://presek.mk/cluster/c-1');
  assert.equal(buildEmbedClusterUrl('c-1', 'sr'), 'https://presek.live/cluster/c-1');
});

test('buildEmbedTrustViewModel maps cluster fixture contract', () => {
  const vm = buildEmbedTrustViewModel(fixture.data, 'sr', 'cluster-42');
  assert.equal(vm.headline, 'Vlada usvojila izmene zakona');
  assert.equal(vm.trustChip.sourcesCount, 3);
  assert.equal(vm.trustSummary.tier, 'verified');
  assert.match(vm.clusterUrl, /presek\.live\/cluster\/cluster-42/);
  assert.ok(vm.detail);
});
