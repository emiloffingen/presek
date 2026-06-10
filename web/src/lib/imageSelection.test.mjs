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
  assert.match(selected.proxiedUrl, /lang=sr/);
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

test('chooseClusterImage passes lang to proxy fallback', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-mk',
    synthetic_headline: 'Тест наслов',
    articles: [{ category: 'Политика', source: 'MIA' }],
  }, 'card', 'mk');

  assert.match(selected.fallbackUrl, /lang=mk/);
  assert.match(selected.proxiedUrl, /lang=mk/);
});

test('staticFallbackUrl matches proxy fallbackUrl', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-3',
    synthetic_headline: 'Fallback alias check',
    articles: [{ category: 'Sport', source: 'Portal' }],
  });

  assert.equal(selected.staticFallbackUrl, selected.fallbackUrl);
  assert.match(selected.fallbackUrl, /^\/proxy\?/);
});
