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
          category: 'Srbija',
          primarySource: 'Republika',
          sources: ['Republika', 'Press24'],
          tags: ['Влада'],
          viewedAt: '2026-04-10T10:00:00Z',
        },
        {
          cluster_id: 'b',
          topic: 'Политика',
          category: 'Srbija',
          primarySource: 'Press24',
          sources: ['Press24', 'Kanal 5'],
          tags: ['Влада', 'Собрание'],
          viewedAt: '2026-04-10T11:00:00Z',
        },
        {
          cluster_id: 'c',
          topic: 'Економија',
          category: 'Srbija',
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
          category: 'Srbija',
          primarySource: 'Skopje Info',
          sources: ['Skopje Info', 'MKD'],
          tags: ['Скопје'],
          viewedAt: '2026-04-10T09:00:00Z',
        },
        {
          cluster_id: 'e',
          topic: 'Живот',
          category: 'Srbija',
          primarySource: 'Libertas',
          sources: ['Libertas', 'Kanal 5'],
          tags: ['Велигден'],
          viewedAt: '2026-04-10T10:00:00Z',
        },
        {
          cluster_id: 'f',
          topic: 'Политика',
          category: 'Srbija',
          primarySource: 'Press24',
          sources: ['Press24', 'Republika'],
          tags: ['Мицкоски'],
          viewedAt: '2026-04-10T11:00:00Z',
        },
        {
          cluster_id: 'g',
          topic: 'Скопје',
          category: 'Srbija',
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
          category: 'Srbija',
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
          topic: 'Srbija',
          category: 'Srbija',
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
          category: 'Srbija',
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
          category: 'Srbija',
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
          tags: ['Системски'],
          viewedAt: '2026-04-10T09:00:00Z',
        },
        {
          cluster_id: 'o',
          topic: 'Скопје',
          category: 'Srbija',
          primarySource: 'Skopje Info',
          sources: ['Skopje Info', 'Kanal 5'],
          tags: ['Транспорт'],
          viewedAt: '2026-04-10T10:30:00Z',
        },
        {
          cluster_id: 'p',
          topic: 'Политика',
          category: 'Srbija',
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

  // Extract real topics, sources, and tags from fetched clusters
  const realTopics = Array.from(new Set(clusters.map(c => c.articles?.[0]?.topic).filter(Boolean)));
  const realSources = Array.from(new Set(clusters.flatMap(c => c.articles?.map(a => a.source).filter(Boolean) || [])));
  const realTags = Array.from(new Set(clusters.flatMap(c => c.tags || [])));

  const isWeak = (val) => {
    const clean = String(val || '').replace(/\s+/g, ' ').trim().toLowerCase();
    return ['vesti', 'srbija', 'svet', 'balkan', 'sport', 'kultura', 'tehnologija', 'zivot'].includes(clean);
  };

  const nonWeakTopics = realTopics.filter(t => !isWeak(t));
  const topic1 = nonWeakTopics[0] || 'Politika';
  const topic2 = nonWeakTopics[1] || 'Ekonomija';
  const source1 = realSources[0] || 'Nedeljnik';
  const source2 = realSources[1] || 'danas';
  const tag1 = realTags[0] || 'Vlada';

  const now = new Date();
  const oneHourAgo = new Date(now - 3600000).toISOString();
  const twoHoursAgo = new Date(now - 7200000).toISOString();

  const dynamicProfiles = [
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
            cluster_id: 'mock-a',
            topic: topic1,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1, source2],
            tags: [tag1],
            viewedAt: oneHourAgo,
          },
          {
            cluster_id: 'mock-b',
            topic: topic1,
            category: 'Srbija',
            primarySource: source2,
            sources: [source2],
            tags: [tag1],
            viewedAt: twoHoursAgo,
          },
        ],
        followedTopics: [topic1],
        followedSources: [source1],
      },
    },
    {
      name: 'broad_reader',
      profile: {
        recentClusters: [
          {
            cluster_id: 'mock-c',
            topic: topic2,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1],
            tags: [],
            viewedAt: oneHourAgo,
          },
          {
            cluster_id: 'mock-d',
            topic: topic1,
            category: 'Srbija',
            primarySource: source2,
            sources: [source2],
            tags: [],
            viewedAt: twoHoursAgo,
          },
        ],
        followedTopics: [topic2],
        followedSources: [],
      },
    },
    {
      name: 'source_loyal',
      profile: {
        recentClusters: [
          {
            cluster_id: 'mock-e',
            topic: topic1,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1],
            tags: [],
            viewedAt: oneHourAgo,
          },
          {
            cluster_id: 'mock-f',
            topic: topic2,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1],
            tags: [],
            viewedAt: twoHoursAgo,
          },
        ],
        followedTopics: [],
        followedSources: [source1],
      },
    },
    {
      name: 'stale_history',
      profile: {
        recentClusters: [
          {
            cluster_id: 'mock-g',
            topic: topic1,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1],
            tags: [],
            viewedAt: new Date(now - 80 * 24 * 3600 * 1000).toISOString(),
          },
        ],
        followedTopics: [topic1],
        followedSources: [],
      },
    },
    {
      name: 'mixed_intent',
      profile: {
        recentClusters: [
          {
            cluster_id: 'mock-h',
            topic: topic1,
            category: 'Srbija',
            primarySource: source1,
            sources: [source1],
            tags: [],
            viewedAt: oneHourAgo,
          },
          {
            cluster_id: 'mock-i',
            topic: topic2,
            category: 'Srbija',
            primarySource: source2,
            sources: [source2],
            tags: [],
            viewedAt: twoHoursAgo,
          },
        ],
        followedTopics: [topic1],
        followedSources: [source1],
      },
    },
  ];

  const results = dynamicProfiles.map(({ name, profile }) => ({
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
