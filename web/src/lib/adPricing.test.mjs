import test from 'node:test';
import assert from 'node:assert/strict';
import { slotName, formatDateDmy, promoNote, SLOT_NAMES } from './adPricing.ts';

test('every placement has one name in both languages', () => {
  for (const lang of ['mk', 'sr']) {
    for (const slot of ['top_banner', 'sidebar', 'mobile_content']) {
      assert.ok(slotName(slot, lang).trim(), `${lang}.${slot}`);
    }
  }
  assert.equal(Object.keys(SLOT_NAMES.mk).length, 3);
});

test('dates are written day.month.year', () => {
  assert.equal(formatDateDmy('2026-10-17'), '17.10.2026');
  assert.equal(formatDateDmy(''), '');
  assert.equal(formatDateDmy('garbage'), '');
});

test('the promo note does not imply a deadline unless one is configured', () => {
  const note = promoNote('mk');
  assert.match(note, /^−\d+% од редовната цена/);
  assert.ok(!note.includes('·'), 'no end date configured, so no "until" clause');
});
