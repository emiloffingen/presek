import test from 'node:test';
import assert from 'node:assert/strict';

import { buildTopicConnections } from './topicDiscovery.js';

test('buildTopicConnections ranks shared-context topics first', () => {
  const clusters = [
    {
      articles: [{ source: 'MIA' }, { source: 'Telma' }],
    },
    {
      articles: [{ source: 'MIA' }, { source: 'Sitel' }],
    },
    {
      articles: [{ source: 'Kanal 5' }],
    },
  ];

  const details = [
    { topics: ['Politika', 'Ekonomija'], tags: ['Budžet', 'Skupština'] },
    { topics: ['Politika', 'Ekonomija'], tags: ['Budžet', 'Ministarstvo'] },
    { topics: ['Politika', 'Obrazovanje'], tags: ['Univerzitet'] },
  ];

  const result = buildTopicConnections('Politika', clusters, details, 3);

  assert.equal(result[0].topic, 'Ekonomija');
  assert.equal(result[1].topic, 'Obrazovanje');
});

test('buildTopicConnections skips the current topic and preserves sample tags', () => {
  const clusters = [
    {
      articles: [{ source: 'MIA' }, { source: 'Alsat' }],
    },
  ];

  const details = [
    { topics: ['Svet', 'Bezbednost'], tags: ['NATO', 'Samit', 'EU'] },
  ];

  const result = buildTopicConnections('Svet', clusters, details, 3);

  assert.equal(result.length, 1);
  assert.equal(result[0].topic, 'Bezbednost');
  assert.deepEqual(result[0].sampleTags, ['NATO', 'Samit', 'EU']);
});
