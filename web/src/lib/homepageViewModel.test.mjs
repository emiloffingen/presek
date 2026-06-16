import test from 'node:test';
import assert from 'node:assert/strict';
import { buildHomepageViewModel } from './homepageViewModel.ts';
import { normalizeHomeApiResponse } from './homepageData.ts';

const HOME_FIXTURE = {
  status: 'success',
  lead: {
    cluster_id: 'lead-1',
    synthetic_headline: 'Vlada usvojila izmene',
    articles: [{ title: 'Vlada', source: 'RTS', category: 'Politika' }],
    sources_count: 4,
  },
  supporting: [],
  developing: [],
  wire: [],
  for_you_pool: [{ cluster_id: 'fy-1', articles: [{ title: 'Za vas', source: 'Danas' }] }],
  synthesis_picks: [{ cluster_id: 'syn-1', articles: [{ title: 'Sinteza', source: 'RTS' }] }],
  trending: [{ cluster_id: 't-1' }],
  focus_entities: [],
  stats: { intelligence: { pluralism: { pluralism_pct: 37 } } },
  briefing: { date: '2026-06-16', content: '## Šta pokreće dan\n\nGlavna vest.' },
  lead_display: { title: 'Vlada usvojila izmene', summary: 'Parlament je doneo izmene.' },
  pipeline: { busy: false },
  excluded_cluster_ids: [],
};

test('buildHomepageViewModel maps fixture into analysis nav', () => {
  const homepageState = {
    ...normalizeHomeApiResponse(HOME_FIXTURE),
    error: null,
  };
  const vm = buildHomepageViewModel({
    homepageState,
    isHomepage: true,
    isSimpleHomepage: false,
    lang: 'sr',
    filters: {
      category: null,
      topic: null,
      entity: null,
      subcategory: null,
      q: null,
      timespan: null,
      isHomepage: true,
    },
    t: (key) => key,
    localePath: (p) => p,
  });

  assert.equal(vm.leadCluster?.cluster_id, 'lead-1');
  assert.ok(vm.displayedSynthesisPicks.length >= 1);
  assert.ok(vm.analizaNavItems.length >= 2);
  assert.equal(vm.pluralismPct, 37);
  assert.equal(vm.showAnalysisLayers, true);
  assert.equal(typeof vm.getTimeStr, 'function');
  assert.ok(vm.getTimeStr('2026-06-16T12:00:00Z').length > 0);
});
