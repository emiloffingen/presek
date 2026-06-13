import test from 'node:test';
import assert from 'node:assert/strict';
import { trustChipFixtures, freshnessFixtures } from './trustFreshnessFixtures.ts';
import { buildTrustChip } from './trustSignals.ts';
import { formatStoryFreshness } from '../utils/storyFreshness.ts';

const t = (key, params = {}) => {
  const catalog = {
    'news.just_now': 'just now',
    'news.ago': 'ago',
    'news.min_short': 'min',
    'news.hour': 'hour',
    'news.hours': 'hours',
    'news.day': 'day',
    'news.days': 'days',
    'freshness.updated': 'Updated {time}',
    'freshness.stale_updating': 'Synthesis updating',
    'freshness.pending_synthesis': 'Synthesis pending',
    'freshness.stale_new_reports': '+{count} new reports',
  };
  let value = catalog[key] || key;
  for (const [paramKey, paramValue] of Object.entries(params)) {
    value = value.replaceAll(`{${paramKey}}`, String(paramValue));
  }
  return value;
};

test('trustFreshnessFixtures cover pending synthesis trust chip', () => {
  const pending = trustChipFixtures.find((fixture) => fixture.id === 'pending-synthesis');
  assert.ok(pending);
  const chip = buildTrustChip(pending.props, 'sr');
  assert.equal(chip.label, 'U pripremi');
});

test('trustFreshnessFixtures cover pending freshness badge tone', () => {
  const pending = freshnessFixtures.find((fixture) => fixture.id === 'pending');
  assert.ok(pending);
  const view = formatStoryFreshness(pending.input, t);
  assert.equal(view?.tone, 'pending');
  assert.equal(view?.label, 'Synthesis pending');
});

test('trustFreshnessFixtures include stale refresh states', () => {
  assert.ok(freshnessFixtures.some((fixture) => fixture.id === 'stale-updating'));
  assert.ok(trustChipFixtures.some((fixture) => fixture.id === 'stale-refresh'));
});
