import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getConsensusNote,
  resolveHasCitationSources,
  shouldShowConsensusNote,
  shouldShowCredibilitySection,
  shouldShowExecutiveSummary,
  shouldShowHeroVisual,
  shouldShowKeyFactsBand,
  shouldShowPerspectives,
} from './clusterPageLayout.ts';

const freshSynthesis = {
  hasGeneratedNarrative: true,
  synthesisFreshness: { is_stale: false, reasons: [] },
  hasFactcheck: false,
  conflictsCount: 0,
  pluralismScore: null,
  uniqueSourcesCount: 8,
  leadVisualIsWeak: true,
};

test('executive summary hides when fresh generated narrative exists', () => {
  assert.equal(
    shouldShowExecutiveSummary({
      ...freshSynthesis,
      hasBriefItems: true,
      hasKeyFacts: true,
    }),
    false,
  );
});

test('executive summary shows when synthesis is stale or missing', () => {
  assert.equal(
    shouldShowExecutiveSummary({
      ...freshSynthesis,
      synthesisFreshness: { is_stale: true, reasons: [] },
      hasKeyFacts: true,
    }),
    true,
  );
  assert.equal(
    shouldShowExecutiveSummary({
      ...freshSynthesis,
      hasGeneratedNarrative: false,
      hasBriefItems: true,
    }),
    true,
  );
});

test('hero hides for weak lead visuals', () => {
  assert.equal(shouldShowHeroVisual(freshSynthesis), false);
  assert.equal(shouldShowHeroVisual({ ...freshSynthesis, leadVisualIsWeak: false }), true);
});

test('perspectives hide on echo-chamber clusters without pluralism conflicts', () => {
  assert.equal(shouldShowPerspectives(freshSynthesis), false);
  assert.equal(shouldShowConsensusNote(freshSynthesis), true);
  assert.equal(shouldShowCredibilitySection(freshSynthesis), true);
});

test('perspectives show when pluralism or conflicts are real', () => {
  assert.equal(
    shouldShowPerspectives({ ...freshSynthesis, pluralismScore: 62 }),
    true,
  );
  assert.equal(
    shouldShowPerspectives({ ...freshSynthesis, conflictsCount: 2 }),
    true,
  );
  assert.equal(
    shouldShowConsensusNote({ ...freshSynthesis, pluralismScore: 62 }),
    false,
  );
});

test('citation sources resolve from API payload', () => {
  assert.equal(resolveHasCitationSources([]), false);
  assert.equal(resolveHasCitationSources([{ index: 1 }]), true);
});

test('consensus note is localized', () => {
  assert.match(getConsensusNote('mk'), /Изворите/);
  assert.match(getConsensusNote('sr'), /Izvori/);
});

test('key facts band shows only with fresh synthesis outside executive summary', () => {
  assert.equal(
    shouldShowKeyFactsBand({
      hasGeneratedNarrative: true,
      hasKeyFacts: true,
      showExecutiveSummary: false,
    }),
    true,
  );
  assert.equal(
    shouldShowKeyFactsBand({
      hasGeneratedNarrative: true,
      hasKeyFacts: true,
      showExecutiveSummary: true,
    }),
    false,
  );
  assert.equal(
    shouldShowKeyFactsBand({
      hasGeneratedNarrative: false,
      hasKeyFacts: true,
      showExecutiveSummary: true,
    }),
    false,
  );
});
