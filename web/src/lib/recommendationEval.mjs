import {
  buildPersonalizedClusters,
  buildSurfaceFollowSuggestions,
} from './personalization.js';

export const DEFAULT_RECOMMENDATION_EVAL_URL =
  process.env.API_URL || 'http://127.0.0.1:5001/api/news?page_size=12';

export const SAMPLE_PROFILES = [
  {
    name: 'cold_start',
    profile: {
      recentClusters: [],
      followedTopics: [],
      followedSources: [],
    },
  },
  {
    name: 'topic_heavy',
    profile: {
      recentClusters: [
        {
          cluster_id: 'a',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Republika',
          sources: ['Republika', 'Press24'],
          tags: ['Влада'],
          viewedAt: '2026-04-10T10:00:00Z',
        },
        {
          cluster_id: 'b',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Press24',
          sources: ['Press24', 'Kanal 5'],
          tags: ['Влада', 'Собрание'],
          viewedAt: '2026-04-10T11:00:00Z',
        },
        {
          cluster_id: 'c',
          topic: 'Економија',
          category: 'Македонија',
          primarySource: 'Republika',
          sources: ['Republika', 'MKD'],
          tags: ['Инфлација'],
          viewedAt: '2026-04-10T12:00:00Z',
        },
      ],
      followedTopics: ['Политика'],
      followedSources: ['Republika'],
    },
  },
  {
    name: 'broad_reader',
    profile: {
      recentClusters: [
        {
          cluster_id: 'd',
          topic: 'Скопје',
          category: 'Македонија',
          primarySource: 'Skopje Info',
          sources: ['Skopje Info', 'MKD'],
          tags: ['Скопје'],
          viewedAt: '2026-04-10T09:00:00Z',
        },
        {
          cluster_id: 'e',
          topic: 'Живот',
          category: 'Македонија',
          primarySource: 'Libertas',
          sources: ['Libertas', 'Kanal 5'],
          tags: ['Велигден'],
          viewedAt: '2026-04-10T10:00:00Z',
        },
        {
          cluster_id: 'f',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Press24',
          sources: ['Press24', 'Republika'],
          tags: ['Мицкоски'],
          viewedAt: '2026-04-10T11:00:00Z',
        },
        {
          cluster_id: 'g',
          topic: 'Скопје',
          category: 'Македонија',
          primarySource: 'Skopje Info',
          sources: ['Skopje Info', 'Kanal 5'],
          tags: ['Транспорт'],
          viewedAt: '2026-04-10T12:00:00Z',
        },
      ],
      followedTopics: ['Скопје'],
      followedSources: [],
    },
  },
  {
    name: 'source_loyal',
    profile: {
      recentClusters: [
        {
          cluster_id: 'h',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Kanal 5',
          sources: ['Kanal 5', 'Press24'],
          tags: ['Влада'],
          viewedAt: '2026-04-09T08:00:00Z',
        },
        {
          cluster_id: 'i',
          topic: 'Свет',
          category: 'Свет',
          primarySource: 'Kanal 5',
          sources: ['Kanal 5', 'Republika'],
          tags: ['Иран'],
          viewedAt: '2026-04-09T09:00:00Z',
        },
        {
          cluster_id: 'j',
          topic: 'Македонија',
          category: 'Македонија',
          primarySource: 'Kanal 5',
          sources: ['Kanal 5', 'MKD'],
          tags: ['Скопје'],
          viewedAt: '2026-04-09T10:00:00Z',
        },
      ],
      followedTopics: [],
      followedSources: ['Kanal 5'],
    },
  },
  {
    name: 'stale_history',
    profile: {
      recentClusters: [
        {
          cluster_id: 'k',
          topic: 'Економија',
          category: 'Македонија',
          primarySource: 'Republika',
          sources: ['Republika', 'Press24'],
          tags: ['Буџет'],
          viewedAt: '2026-03-20T09:00:00Z',
        },
        {
          cluster_id: 'l',
          topic: 'Спорт',
          category: 'Спорт',
          primarySource: 'MKD',
          sources: ['MKD', 'Kanal 5'],
          tags: ['Фудбал'],
          viewedAt: '2026-03-21T10:00:00Z',
        },
      ],
      followedTopics: ['Економија'],
      followedSources: [],
    },
  },
  {
    name: 'mixed_intent',
    profile: {
      recentClusters: [
        {
          cluster_id: 'm',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Press24',
          sources: ['Press24', 'Republika'],
          tags: ['Мицкоски'],
          viewedAt: '2026-04-10T08:30:00Z',
        },
        {
          cluster_id: 'n',
          topic: 'Технологија',
          category: 'Свет',
          primarySource: 'MKD',
          sources: ['MKD', 'Press24'],
          tags: ['AI'],
          viewedAt: '2026-04-10T09:00:00Z',
        },
        {
          cluster_id: 'o',
          topic: 'Скопје',
          category: 'Македонија',
          primarySource: 'Skopje Info',
          sources: ['Skopje Info', 'Kanal 5'],
          tags: ['Транспорт'],
          viewedAt: '2026-04-10T10:30:00Z',
        },
        {
          cluster_id: 'p',
          topic: 'Политика',
          category: 'Македонија',
          primarySource: 'Republika',
          sources: ['Republika', 'Kanal 5'],
          tags: ['Влада'],
          viewedAt: '2026-04-10T11:30:00Z',
        },
      ],
      followedTopics: ['Политика'],
      followedSources: ['Skopje Info'],
    },
  },
];

function compactCluster(item) {
  return {
    id: item.cluster.cluster_id,
    title: item.cluster.articles?.[0]?.title || '',
    reason: item.reason,
    score: Number(item.score.toFixed(2)),
  };
}

export async function getRecommendationEvaluation(apiUrl = DEFAULT_RECOMMENDATION_EVAL_URL) {
  const response = await fetch(apiUrl);
  if (!response.ok) {
    throw new Error(`Failed to fetch clusters: ${response.status} ${apiUrl}`);
  }

  const payload = await response.json();
  const clusters = Array.isArray(payload?.clusters) ? payload.clusters : [];

  const results = SAMPLE_PROFILES.map(({ name, profile }) => ({
    profile: name,
    personalized: buildPersonalizedClusters(clusters, profile, 4).map(compactCluster),
    home_rail: buildSurfaceFollowSuggestions(profile, 'home_rail', { topicLimit: 2, sourceLimit: 1 }),
    for_you: buildSurfaceFollowSuggestions(profile, 'for_you', { topicLimit: 2, sourceLimit: 1 }),
    topic: buildSurfaceFollowSuggestions(profile, 'topic', { topicLimit: 2, sourceLimit: 1 }),
  }));

  return {
    api_url: apiUrl,
    cluster_count: clusters.length,
    results,
  };
}

async function main() {
  const evaluation = await getRecommendationEvaluation();
  console.log(JSON.stringify(evaluation, null, 2));
}

const isCliEntry = process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href;

if (isCliEntry) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
