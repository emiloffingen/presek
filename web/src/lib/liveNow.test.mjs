import test from 'node:test';
import assert from 'node:assert/strict';

import { isLiveNowCandidate, rankLiveNowClusters, isLatestWireArticleCandidate, rankLatestWireArticles } from './liveNow.js';

function cluster({
  cluster_id,
  title,
  source = 'MIA',
  topic = 'Политика',
  category = 'Македонија',
  created_at = '2026-04-22T18:00:00Z',
  is_breaking = false,
  articles = 2,
} = {}) {
  return {
    cluster_id,
    is_breaking,
    articles: Array.from({ length: articles }, (_, index) => ({
      title: index === 0 ? title : `${title} / corroboration`,
      source,
      topic,
      category,
      created_at,
    })),
  };
}

test('live-now rejects feature and clickbait style titles', () => {
  assert.equal(
    isLiveNowCandidate(cluster({
      cluster_id: 'a1',
      title: 'Постојано сте уморни, проверете дали ви недостига овој минерал',
      topic: 'Здравје',
      articles: 1,
    })),
    false
  );

  assert.equal(
    isLiveNowCandidate(cluster({
      cluster_id: 'a2',
      title: 'Издание на 360°: интервју со министерот Азир Алиу',
      topic: 'Политика',
      articles: 1,
    })),
    false
  );
});

test('live-now keeps hard-news arrivals and breaking items', () => {
  assert.equal(
    isLiveNowCandidate(cluster({
      cluster_id: 'b1',
      title: 'Собранието расправа за нов буџет и пакет мерки',
      topic: 'Економија',
      articles: 1,
    })),
    true
  );

  assert.equal(
    isLiveNowCandidate(cluster({
      cluster_id: 'b2',
      title: 'Вардар победи 2-0 во дербито',
      topic: 'Спорт',
      is_breaking: true,
      articles: 1,
    })),
    true
  );
});

test('live-now ranking prefers breaking, excludes duplicates by source, and filters junk', () => {
  const ranked = rankLiveNowClusters([
    cluster({
      cluster_id: 'c1',
      title: 'Издание на 360°: интервју со министерот',
      source: '360 Stepeni',
      topic: 'Политика',
      created_at: '2026-04-22T18:10:00Z',
      articles: 1,
    }),
    cluster({
      cluster_id: 'c2',
      title: 'Владата носи итни мерки по новата седница',
      source: 'MIA',
      topic: 'Политика',
      is_breaking: true,
      created_at: '2026-04-22T18:20:00Z',
      articles: 1,
    }),
    cluster({
      cluster_id: 'c3',
      title: 'Собранието отвори расправа за буџетот',
      source: 'MIA',
      topic: 'Економија',
      created_at: '2026-04-22T18:15:00Z',
      articles: 2,
    }),
    cluster({
      cluster_id: 'c4',
      title: 'Обвинителството отвори истрага за набавките',
      source: 'Alsat-M',
      topic: 'Криминал',
      created_at: '2026-04-22T18:18:00Z',
      articles: 2,
    }),
  ]);

  assert.deepEqual(ranked.map((item) => item.cluster_id), ['c2', 'c4']);
});

test('latest wire rejects wellness clickbait and interview features', () => {
  assert.equal(
    isLatestWireArticleCandidate({
      title: 'Постојано сте уморни, проверете дали ви недостига овој минерал',
      topic: 'Здравје',
      category: 'Македонија',
    }),
    false
  );

  assert.equal(
    isLatestWireArticleCandidate({
      title: 'Издание на 360°: интервју со министерот Азир Алиу',
      topic: 'Политика',
      category: 'Македонија',
    }),
    false
  );
});

test('latest wire keeps hard-news items and sorts them ahead of softer ones', () => {
  const ranked = rankLatestWireArticles([
    {
      title: 'Постојано сте уморни, проверете дали ви недостига овој минерал',
      topic: 'Здравје',
      category: 'Македонија',
      source: 'Expres',
      created_at: '2026-04-22T15:57:00Z',
    },
    {
      title: 'Реакција на кинеската компанија Синохидро на изјавата на Николоски',
      topic: 'Политика',
      category: 'Македонија',
      source: 'Sloboden Pecat',
      created_at: '2026-04-22T13:35:00Z',
    },
    {
      title: 'Тешка сообраќајка на експресниот пат кај Ранковце',
      topic: 'Криминал',
      category: 'Македонија',
      source: 'Kanal 5',
      created_at: '2026-04-22T12:59:00Z',
    },
  ], 10);

  assert.deepEqual(
    ranked.map((item) => item.title),
    [
      'Реакција на кинеската компанија Синохидро на изјавата на Николоски',
      'Тешка сообраќајка на експресниот пат кај Ранковце',
    ]
  );
});
