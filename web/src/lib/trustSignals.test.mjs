import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTrustChip } from './trustSignals.ts';

test('buildTrustChip shows pending label when synthesis is missing', () => {
  const chip = buildTrustChip(
    { sourcesCount: 3, isPendingSynthesis: true, quietFreshness: true },
    'mk',
  );
  assert.equal(chip.label, 'Се подготвува');
  assert.match(chip.detail, /генерира/);
});

test('buildTrustChip keeps stale note for refresh stale synthesis', () => {
  const chip = buildTrustChip(
    { sourcesCount: 3, isStale: true },
    'sr',
  );
  assert.match(chip.detail, /osvežava/);
});
