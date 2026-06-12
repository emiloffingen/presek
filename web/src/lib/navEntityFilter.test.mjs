import test from 'node:test';
import assert from 'node:assert/strict';
import { isNavWorthyEntity, filterTrendingNavItems } from './navEntityFilter.ts';

test('isNavWorthyEntity rejects headline noise', () => {
  assert.equal(isNavWorthyEntity('Evo'), false);
  assert.equal(isNavWorthyEntity('#Ovo'), false);
  assert.equal(isNavWorthyEntity('Srbiji'), false);
  assert.equal(isNavWorthyEntity('vesti'), false);
});

test('isNavWorthyEntity keeps meaningful entities', () => {
  assert.equal(isNavWorthyEntity('Vučić'), true);
  assert.equal(isNavWorthyEntity('Evropska unija'), true);
  assert.equal(isNavWorthyEntity('Donald Trump'), true);
});

test('filterTrendingNavItems only filters trending tags', () => {
  const items = [
    { label: 'Politika', type: 'topic' },
    { label: '#Evo', type: 'trending_tag' },
    { label: 'Vučić', type: 'trending_tag' },
  ];
  const filtered = filterTrendingNavItems(items);
  assert.deepEqual(filtered, [
    { label: 'Politika', type: 'topic' },
    { label: 'Vučić', type: 'trending_tag' },
  ]);
});
