import test from 'node:test';
import assert from 'node:assert/strict';
import { getVisibleCardSignals } from './signalBadges.ts';

test('shows conflict badge for high pluralism', () => {
  const badges = getVisibleCardSignals({ pluralismScore: 72, pulseScore: 40, topic: 'Politika' });
  assert.equal(badges[0]?.key, 'pluralism-conflict');
});

test('shows consensus badge for low pluralism', () => {
  const badges = getVisibleCardSignals({ pluralismScore: 10, pulseScore: 40, topic: 'Politika' });
  assert.equal(badges[0]?.key, 'pluralism-consensus');
});

test('shows pulse badge when hot', () => {
  const badges = getVisibleCardSignals({ pluralismScore: 30, pulseScore: 90, topic: 'Sport' });
  assert.ok(badges.some((badge) => badge.key === 'pulse-hot'));
});

test('falls back to topic when no notable signals', () => {
  const badges = getVisibleCardSignals({ pluralismScore: 30, pulseScore: 50, topic: 'Ekonomija' });
  assert.equal(badges[0]?.key, 'topic');
});
