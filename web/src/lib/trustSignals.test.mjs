import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTrustChip, buildCompactPluralismMeta, buildPrimaryCardBadge } from './trustSignals.ts';

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
    'mk',
  );
  assert.match(chip.detail, /освежува/);
});

test('buildTrustChip shows provisional label when synthesis needs upgrade', () => {
  const chip = buildTrustChip(
    { sourcesCount: 4, isProvisional: true },
    'mk',
  );
  assert.equal(chip.label, 'Привремен преглед');
  assert.equal(chip.isProvisional, true);
});

test('buildCompactPluralismMeta highlights plural coverage on compact cards', () => {
  const meta = buildCompactPluralismMeta({ sourcesCount: 4, pluralismScore: 62 }, 'mk');
  assert.match(meta, /Различни агли/);
  assert.match(meta, /62%/);
});

test('buildCompactPluralismMeta shows consensus label', () => {
  const meta = buildCompactPluralismMeta({ sourcesCount: 5, pluralismScore: 10 }, 'mk');
  assert.match(meta, /Консензус/);
  assert.match(meta, /5 изв\./);
});

test('buildPrimaryCardBadge shows early signal for single source', () => {
  const badge = buildPrimaryCardBadge({ sourcesCount: 1 }, 'mk');
  assert.match(badge, /Ран сигнал/);
  assert.match(badge, /1 извор/);
});
