import test from 'node:test';
import assert from 'node:assert/strict';

import { about } from './about.ts';
import { archive } from './archive.ts';
import { cluster } from './cluster.ts';
import { common } from './common.ts';
import { editorial } from './editorial.ts';
import { entity } from './entity.ts';
import { home } from './home.ts';
import { methodology } from './methodology.ts';
import { nav } from './nav.ts';
import { news } from './news.ts';
import { search } from './search.ts';
import { settings } from './settings.ts';
import { sources } from './sources.ts';

const namespaces = { about, archive, cluster, common, editorial, entity, home, methodology, nav, news, search, settings, sources };

// Letters that never occur in literary Macedonian (Russian/Bulgarian/Serbian/
// Ukrainian). Catches slips like "Скрий" (Russian й) or "соодветния" (bg я).
const FORBIDDEN = /[йяюыэёђћіїєґъ]/i;

test('no i18n string uses a letter outside the Macedonian alphabet', () => {
  const hits = [];
  for (const [ns, mod] of Object.entries(namespaces)) {
    for (const [key, value] of Object.entries(mod.mk)) {
      if (typeof value === 'string' && FORBIDDEN.test(value)) {
        hits.push(`${ns}.${key}: ${value}`);
      }
    }
  }
  assert.equal(hits.length, 0, `non-Macedonian letters found:\n${hits.join('\n')}`);
});
