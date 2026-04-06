import test from 'node:test';
import assert from 'node:assert/strict';

import { genericAskError, normalizeAskErrorMessage } from './askPresekErrors.js';

test('maps raw internal server error to the generic Macedonian message', () => {
  assert.equal(normalizeAskErrorMessage('Internal Server Error'), genericAskError);
});

test('maps html error pages to the generic Macedonian message', () => {
  assert.equal(
    normalizeAskErrorMessage('<!doctype html><html><body>500</body></html>'),
    genericAskError
  );
});

test('maps known backend failure strings to the generic Macedonian message', () => {
  assert.equal(normalizeAskErrorMessage('Failed to process query'), genericAskError);
  assert.equal(normalizeAskErrorMessage('Failed to fetch'), genericAskError);
});

test('maps 5xx statuses to the generic Macedonian message even for other text', () => {
  assert.equal(normalizeAskErrorMessage('Server exploded', 503), genericAskError);
});

test('keeps specific user-safe messages unchanged', () => {
  assert.equal(
    normalizeAskErrorMessage('Question is required', 400),
    'Question is required'
  );
});

test('uses the generic message when the input is empty', () => {
  assert.equal(normalizeAskErrorMessage('', 500), genericAskError);
});
