import test from 'node:test';
import assert from 'node:assert/strict';
import { parseTopicParam } from './topicParam.ts';

test('lowercase Latin slugs are capitalised to the stored topic name', () => {
  assert.equal(parseTopicParam('politika'), 'Politika');
  assert.equal(parseTopicParam('  sport '), 'Sport');
  assert.equal(parseTopicParam('crna%20hronika'), 'Crna Hronika');
});

test('already-canonical, Cyrillic and mixed values are left alone', () => {
  assert.equal(parseTopicParam('Politika'), 'Politika');
  assert.equal(parseTopicParam('политика'), 'политика');
  assert.equal(parseTopicParam('NATO'), 'NATO');
  assert.equal(parseTopicParam('Covid-19'), 'Covid-19');
});

test('empty and malformed input does not throw', () => {
  assert.equal(parseTopicParam(undefined), '');
  assert.equal(parseTopicParam(''), '');
  assert.equal(parseTopicParam('100%'), '100%');
});
