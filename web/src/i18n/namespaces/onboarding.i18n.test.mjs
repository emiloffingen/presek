import test from 'node:test';
import assert from 'node:assert/strict';
import { common } from './common.ts';

const onboardingKeys = (locale) =>
  Object.keys(common[locale]).filter((key) => key.startsWith('onboarding.')).sort();

test('onboarding namespace has matching sr/mk keys', () => {
  assert.deepEqual(onboardingKeys('mk'), onboardingKeys('sr'), 'sr and mk onboarding keys must match');
});

test('onboarding namespace has no empty sr/mk strings', () => {
  for (const key of onboardingKeys('sr')) {
    assert.ok(common.sr[key]?.trim(), `sr.${key} is empty`);
    assert.ok(common.mk[key]?.trim(), `mk.${key} is empty`);
  }
});
