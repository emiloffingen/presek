import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildOrganizationSchema,
  buildPageTitle,
  gtagIdForLang,
  resolveLayoutUrls,
  siteDisplayName,
} from './layoutMeta.ts';

test('siteDisplayName returns locale-specific brand', () => {
  assert.equal(siteDisplayName('sr'), 'PRESEK.rs');
  assert.equal(siteDisplayName('mk'), 'PRESEK.mk');
});

test('buildPageTitle appends site name when absent', () => {
  assert.equal(buildPageTitle('Vesti', 'sr'), 'Vesti | PRESEK.rs');
});

test('buildPageTitle replaces embedded Presek brand', () => {
  assert.equal(buildPageTitle('Presek vesti', 'sr'), 'PRESEK.rs vesti');
});

test('resolveLayoutUrls builds canonical and image URLs', () => {
  const urls = resolveLayoutUrls('/vesti', 'sr', '/img/presek_emblem.png');
  assert.equal(urls.siteUrl, 'https://presek.live');
  assert.equal(urls.canonicalUrl, 'https://presek.live/vesti');
  assert.match(urls.imageUrl, /\/img\/presek_emblem\.png$/);
});

test('buildOrganizationSchema includes organization id', () => {
  const schema = buildOrganizationSchema('mk');
  assert.equal(schema['@type'], 'Organization');
  assert.equal(schema['@id'], 'https://presek.mk/#organization');
});

test('gtagIdForLang selects locale property', () => {
  assert.equal(gtagIdForLang('mk'), 'G-YJZH9KK8X9');
  assert.equal(gtagIdForLang('sr'), 'G-SV2R3LZJ5C');
});
