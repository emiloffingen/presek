import test from 'node:test';
import assert from 'node:assert/strict';
import {
  absoluteLocaleUrl,
  buildCanonicalUrl,
  hreflangAlternates,
  homePath,
  isHealthyStatus,
  isMkHost,
  localePath,
  shouldRewriteMkDomainToInternal,
  stripMkPrefix,
  withMkPrefix,
} from './localePaths.ts';

test('stripMkPrefix removes leading /mk', () => {
  assert.equal(stripMkPrefix('/mk'), '/');
  assert.equal(stripMkPrefix('/mk/briefing'), '/briefing');
  assert.equal(stripMkPrefix('/briefing'), '/briefing');
});

test('withMkPrefix adds Astro internal prefix', () => {
  assert.equal(withMkPrefix('/'), '/mk');
  assert.equal(withMkPrefix('/briefing'), '/mk/briefing');
});

test('localePath uses clean paths on presek.mk', () => {
  assert.equal(localePath('/briefing', 'mk', 'presek.mk'), '/briefing');
  assert.equal(localePath('/cluster/abc', 'mk', 'presek.mk'), '/cluster/abc');
  assert.equal(homePath('mk', 'presek.mk'), '/');
});

test('localePath keeps /mk prefix on presek.live', () => {
  assert.equal(localePath('/briefing', 'mk', 'presek.live'), '/mk/briefing');
  assert.equal(homePath('mk', 'presek.live'), '/mk');
});

test('hreflang and canonical URLs use root paths on presek.mk', () => {
  assert.deepEqual(hreflangAlternates('/mk/briefing'), {
    sr: 'https://presek.live/briefing',
    mk: 'https://presek.mk/briefing',
  });
  assert.equal(buildCanonicalUrl('/mk/cluster/foo', 'mk'), 'https://presek.mk/cluster/foo');
  assert.equal(absoluteLocaleUrl('/mk/briefing', 'mk'), 'https://presek.mk/briefing');
});

test('shouldRewriteMkDomainToInternal skips assets and APIs', () => {
  assert.equal(shouldRewriteMkDomainToInternal('/briefing'), true);
  assert.equal(shouldRewriteMkDomainToInternal('/api/health'), false);
  assert.equal(shouldRewriteMkDomainToInternal('/_astro/foo.js'), false);
  assert.equal(shouldRewriteMkDomainToInternal('/mk/briefing'), false);
});

test('isHealthyStatus accepts healthy and ok', () => {
  assert.equal(isHealthyStatus('healthy'), true);
  assert.equal(isHealthyStatus('ok'), true);
  assert.equal(isHealthyStatus('degraded'), false);
});

test('isMkHost detects Macedonian domains', () => {
  assert.equal(isMkHost('presek.mk'), true);
  assert.equal(isMkHost('www.presek.mk:443'), true);
  assert.equal(isMkHost('presek.live'), false);
});
