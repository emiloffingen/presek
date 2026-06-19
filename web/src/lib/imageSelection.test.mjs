import test from 'node:test';
import assert from 'node:assert/strict';

import { isWeakVisual, scoreImageUrl } from './imageQuality.ts';
import { buildProxySrcSet, buildProxyUrlWithWidth, chooseClusterImage } from '../utils/imageSelection.ts';

test('isWeakVisual keeps generated cover art', () => {
  assert.equal(isWeakVisual('/static/generated/cluster-1.svg'), false);
});

test('isWeakVisual rejects logos and short urls', () => {
  assert.equal(isWeakVisual('https://example.com/logo.png'), true);
  assert.equal(isWeakVisual('https://x.co/a'), true);
});

test('scoreImageUrl prefers larger editorial photos', () => {
  const hero = scoreImageUrl('https://cdn.example.com/hero-1600x900.jpg', 'SDK');
  const thumb = scoreImageUrl('https://cdn.example.com/thumb/logo-small.png', 'Portal');
  assert.ok(hero > thumb);
});

test('buildProxyUrlWithWidth updates width param regardless of order', () => {
  const url = buildProxyUrlWithWidth('/proxy?lang=sr&url=https%3A%2F%2Fexample.com%2Fa.jpg&w=1200', 360);
  assert.match(url, /w=360/);
  assert.doesNotMatch(url, /w=1200/);
});

test('buildProxySrcSet emits width descriptors', () => {
  const srcset = buildProxySrcSet('/proxy?url=https%3A%2F%2Fexample.com%2Fa.jpg&w=720&lang=sr', [360, 720]);
  assert.match(srcset, /360w/);
  assert.match(srcset, /720w/);
});

test('chooseClusterImage dedupes representative and article urls', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-dedupe',
    representative_image: 'https://cdn.example.com/story-1200x800.jpg',
    articles: [{ image_url: 'https://cdn.example.com/story-1200x800.jpg', source: 'Portal' }],
  });

  assert.equal(selected.isWeak, false);
  assert.match(selected.proxiedUrl, /url=https/);
});

test('chooseClusterImage uses branded fallback for weak visuals', () => {
  const selected = chooseClusterImage({
    cluster_id: 'cluster-weak',
    synthetic_headline: 'Logo should not be used',
    representative_image: 'https://example.com/logo.png',
    articles: [{ image_url: 'https://example.com/logo.png', category: 'Politika', source: 'Portal' }],
  });

  assert.equal(selected.isWeak, true);
  assert.match(selected.proxiedUrl, /^\/proxy\?/);
  assert.doesNotMatch(selected.proxiedUrl, /url=https/);
});
