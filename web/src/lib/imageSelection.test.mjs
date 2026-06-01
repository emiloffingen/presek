import test from 'node:test';
import assert from 'node:assert/strict';

import { chooseClusterImage } from '../utils/imageSelection.ts';

test('chooseClusterImage uses story-specific proxy fallback for missing visuals', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-1',
    synthetic_headline: 'Влада ја продолжи мерката',
    articles: [{ category: 'Економија', source: 'MIA' }],
  });

  assert.equal(selected.isWeak, true);
  assert.match(selected.proxiedUrl, /^\/proxy\?/);
  assert.match(selected.proxiedUrl, /cid=cluster-1/);
  assert.match(selected.proxiedUrl, /t=/);
  assert.match(selected.proxiedUrl, /cat=/);
});

test('chooseClusterImage replaces weak source images with smart fallback', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-2',
    synthetic_headline: 'Logo should not be used',
    representative_image: 'https://example.com/logo.png',
    articles: [{ image_url: 'https://example.com/logo.png', category: 'Politika', source: 'Portal' }],
  });

  assert.equal(selected.isWeak, true);
  assert.match(selected.proxiedUrl, /^\/proxy\?/);
  assert.doesNotMatch(selected.proxiedUrl, /url=https/);
});
