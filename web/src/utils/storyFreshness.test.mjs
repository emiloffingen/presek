import test from 'node:test';
import assert from 'node:assert/strict';
import { formatStoryFreshness } from './storyFreshness.ts';

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

test('formatStoryFreshness returns updated label for recent synthesis', () => {
  const recent = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  const view = formatStoryFreshness(
    { lang: 'sr', synthesisUpdatedAt: recent, isStale: false },
    t,
  );
  assert.ok(view);
  assert.match(view.label, /Updated/);
  assert.equal(view.tone, 'fresh');
});

test('formatStoryFreshness returns stale label when synthesis lags', () => {
  const view = formatStoryFreshness(
    { lang: 'mk', synthesisUpdatedAt: new Date().toISOString(), isStale: true, newArticleCount: 2 },
    t,
  );
  assert.ok(view);
  assert.equal(view.label, '+2 new reports');
  assert.equal(view.tone, 'stale');
});

test('formatStoryFreshness shows updating label when pipeline is busy', () => {
  const recent = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  const view = formatStoryFreshness(
    { lang: 'sr', synthesisUpdatedAt: recent, isStale: false, pipelineBusy: true },
    t,
  );
  assert.ok(view);
  assert.equal(view.label, 'Synthesis updating');
  assert.equal(view.tone, 'stale');
});

test('formatStoryFreshness shows pending label when synthesis is missing', () => {
  const view = formatStoryFreshness(
    { lang: 'mk', isStale: true, missingSynthesis: true },
    t,
  );
  assert.ok(view);
  assert.equal(view.label, 'Synthesis pending');
  assert.equal(view.tone, 'pending');
});
