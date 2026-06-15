import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTrustChip, buildCompactPluralismMeta } from './trustSignals.ts';

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

test('buildTrustChip shows provisional label when synthesis needs upgrade', () => {
  const chip = buildTrustChip(
    { sourcesCount: 4, isProvisional: true },
    'sr',
  );
  assert.equal(chip.label, 'Privremeni pregled');
  assert.equal(chip.isProvisional, true);
});

test('buildCompactPluralismMeta highlights plural coverage on compact cards', () => {
  const meta = buildCompactPluralismMeta({ sourcesCount: 4, pluralismScore: 62 }, 'sr');
  assert.match(meta, /Različiti uglovi/);
  assert.match(meta, /62%/);
});

test('buildCompactPluralismMeta shows consensus label', () => {
  const meta = buildCompactPluralismMeta({ sourcesCount: 5, pluralismScore: 10 }, 'sr');
  assert.match(meta, /Konsenzus/);
  assert.match(meta, /5 izv\./);
});
