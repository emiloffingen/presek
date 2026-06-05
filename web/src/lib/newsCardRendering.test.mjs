import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const here = dirname(fileURLToPath(import.meta.url));
const repoWebSrc = resolve(here, '..');

function readComponent(relativePath) {
  return readFileSync(resolve(repoWebSrc, relativePath), 'utf8');
}

test('generic news cards render regular summaries, not synthesis previews', () => {
  const astroCard = readComponent('components/NewsCard.astro');
  const reactCard = readComponent('components/NewsCard.tsx');

  for (const source of [astroCard, reactCard]) {
    assert.match(source, /displaySummary\s*=\s*getCardSummary\(main,\s*isLead\)/);
    assert.doesNotMatch(source, /synthetic_standfirst\s*\|\|\s*getCardSummary/);
    assert.doesNotMatch(source, /premium-synthesis-badge/);
    assert.doesNotMatch(source, /has-synthesis/);
  }
});
