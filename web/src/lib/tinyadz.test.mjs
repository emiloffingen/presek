import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isPremiumAdFreePage,
  shouldShowTinyAdzInlinedAds,
} from './tinyadz.ts';

test('isPremiumAdFreePage blocks reader premium surfaces', () => {
  assert.equal(isPremiumAdFreePage('/for-you'), true);
  assert.equal(isPremiumAdFreePage('/settings'), true);
  assert.equal(isPremiumAdFreePage('/briefing'), true);
  assert.equal(isPremiumAdFreePage('/mk/for-you'), true);
  assert.equal(isPremiumAdFreePage('/cluster/abc'), true);
  assert.equal(isPremiumAdFreePage('/archive'), true);
});

test('shouldShowTinyAdzInlinedAds respects premium page guard', () => {
  assert.equal(
    shouldShowTinyAdzInlinedAds('sr', 'presek.live', '/for-you'),
    false,
  );
  assert.equal(
    shouldShowTinyAdzInlinedAds('mk', 'presek.mk', '/briefing'),
    false,
  );
  assert.equal(
    shouldShowTinyAdzInlinedAds('sr', 'presek.live', '/cluster/abc'),
    false,
  );
});
