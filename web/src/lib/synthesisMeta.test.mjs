import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCopyPurityNote } from './synthesisMeta.ts';

test('buildCopyPurityNote returns null when copy is ok', () => {
  assert.equal(buildCopyPurityNote({ copy_purity_ok: true }, 'sr'), null);
});

test('buildCopyPurityNote maps MK latin leak reason', () => {
  const note = buildCopyPurityNote(
    { copy_purity_ok: false, copy_purity_reason: 'serbian_latin_leaks' },
    'mk',
  );
  assert.match(note, /латинични/);
});

test('buildCopyPurityNote maps SR cyrillic leak reason', () => {
  const note = buildCopyPurityNote(
    { copy_purity_ok: false, copy_purity_reason: 'cyrillic_leaks' },
    'sr',
  );
  assert.match(note, /Ćirilični|ćirilični/i);
});
