import { Article, NewsCluster } from '../types';

export interface ReaderClusterRecord {
  cluster_id: string;
  title: string;
  category: string;
  topic: string;
  primarySource: string;
  sources: string[];
  tags: string[];
  viewedAt: string;
}

export interface ReaderProfile {
  recentClusters: ReaderClusterRecord[];
  followedTopics: string[];
  followedSources: string[];
}

const PROFILE_KEY = 'presek:reader_profile';
const MAX_RECENT = 24;

export const loadReaderProfile = (): ReaderProfile => {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return {
      recentClusters: Array.isArray(parsed.recentClusters) ? parsed.recentClusters : [],
      followedTopics: Array.isArray(parsed.followedTopics) ? parsed.followedTopics : [],
      followedSources: Array.isArray(parsed.followedSources) ? parsed.followedSources : [],
    };
  } catch {
    return { recentClusters: [], followedTopics: [], followedSources: [] };
  }
};

export const saveReaderProfile = (profile: ReaderProfile) => {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {}
};

export const recordClusterView = (cluster: NewsCluster) => {
  const profile = loadReaderProfile();
  const main = cluster.articles[0];
  
  const record: ReaderClusterRecord = {
    cluster_id: cluster.cluster_id,
    title: main.title,
    category: main.category,
    topic: main.topic,
    primarySource: main.source,
    sources: Array.from(new Set(cluster.articles.map(a => a.source))),
    tags: [], // Tags might not be available in basic cluster list, usually enriched in detail
    viewedAt: new Date().toISOString(),
  };

  const nextRecent = [
    record,
    ...profile.recentClusters.filter(r => r.cluster_id !== record.cluster_id)
  ].slice(0, MAX_RECENT);

  saveReaderProfile({ ...profile, recentClusters: nextRecent });
};

export const getPersonalizedClusters = (clusters: NewsCluster[], profile: ReaderProfile, limit = 3) => {
  const signals = {
    topics: new Map<string, number>(),
    sources: new Map<string, number>(),
  };

  profile.recentClusters.forEach(r => {
    signals.topics.set(r.category, (signals.topics.get(r.category) || 0) + 1);
    if (r.topic) signals.topics.set(r.topic, (signals.topics.get(r.topic) || 0) + 1);
    r.sources.forEach(s => signals.sources.set(s, (signals.sources.get(s) || 0) + 1));
  });

  const scored = clusters.map(c => {
    let score = 0;
    const reasons: string[] = [];
    const main = c.articles[0];
    const clusterSources = c.articles.map(a => a.source);

    // Followed matches
    if (profile.followedTopics.includes(main.category)) {
      score += 5;
      reasons.push(`Следена тема: ${main.category}`);
    }
    
    // Implicit interest matches
    const topicCount = (signals.topics.get(main.category) || 0) + (signals.topics.get(main.topic) || 0);
    if (topicCount > 0) {
      score += Math.min(4, topicCount * 1.5);
      reasons.push(`Често читате за ${main.category}`);
    }

    const sourceMatches = clusterSources.filter(s => profile.followedSources.includes(s) || signals.sources.has(s));
    if (sourceMatches.length > 0) {
      score += 3;
      reasons.push(`Од ваши омилени извори`);
    }

    if (c.is_breaking) score += 1;

    return {
      cluster: c,
      score,
      reason: reasons[0] || 'Предлог за Вас'
    };
  });

  return scored
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
};
