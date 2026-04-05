import test from 'node:test';
import assert from 'node:assert/strict';

import { buildTopicConnections } from './topicDiscovery.js';

test('buildTopicConnections ranks breaking and shared-context topics first', () => {
  const clusters = [
    {
      is_breaking: true,
      articles: [{ source: 'MIA' }, { source: 'Телма' }],
    },
    {
      is_breaking: true,
      articles: [{ source: 'MIA' }, { source: 'Сител' }],
    },
    {
      is_breaking: false,
      articles: [{ source: 'Канал 5' }],
    },
  ];

  const details = [
    { topics: ['Политика', 'Економија'], tags: ['Буџет', 'Собрание'] },
    { topics: ['Политика', 'Економија'], tags: ['Буџет', 'Министерство'] },
    { topics: ['Политика', 'Образование'], tags: ['Универзитет'] },
  ];

  const result = buildTopicConnections('Политика', clusters, details, 3);

  assert.equal(result[0].topic, 'Економија');
  assert.equal(result[0].relationshipLabel, 'Следна развојна линија');
  assert.equal(result[1].topic, 'Образование');
});

test('buildTopicConnections skips the current topic and preserves sample tags', () => {
  const clusters = [
    {
      is_breaking: false,
      articles: [{ source: 'MIA' }, { source: 'Alsat' }],
    },
  ];

  const details = [
    { topics: ['Свет', 'Безбедност'], tags: ['НАТО', 'Самит', 'ЕУ'] },
  ];

  const result = buildTopicConnections('Свет', clusters, details, 3);

  assert.equal(result.length, 1);
  assert.equal(result[0].topic, 'Безбедност');
  assert.deepEqual(result[0].sampleTags, ['НАТО', 'Самит', 'ЕУ']);
});

