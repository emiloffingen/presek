import { Cluster, TrendingItem, WeatherData, Article } from '../types';

export const fetchNews = async (page = 0, topic = '', query = '', isSaved = false): Promise<{ data: Cluster[]; has_more: boolean }> => {
  if (isSaved) {
    const savedIds = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
    if (savedIds.length === 0) return { data: [], has_more: false };
    
    const res = await fetch(`/api/news?ids=${savedIds.join(',')}`);
    const data = await res.json();
    return { data: data.clusters || [], has_more: false };
  }

  const params = new URLSearchParams({
    page: page.toString(),
    page_size: '20'
  });

  if (topic) params.set('topic', topic);
  if (query) params.set('q', query);

  const res = await fetch(`/api/news?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  if (data.status === 'success') {
    return { 
      data: data.data || [], 
      has_more: data.meta?.has_more || false 
    };
  }
  
  throw new Error(data.message || 'Unknown error');
};

export const fetchTrending = async (): Promise<TrendingItem[]> => {
  const res = await fetch('/api/trending');
  if (!res.ok) return [];
  return res.json();
};

export const fetchWeather = async (): Promise<WeatherData | null> => {
  try {
    const res = await fetch('/api/weather');
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
};

export interface BriefingData {
  date: string;
  content: string;
  error?: string;
}

export const fetchBriefing = async (): Promise<BriefingData> => {
  const res = await fetch('/api/briefing');
  if (!res.ok) throw new Error('Failed to fetch briefing');
  return res.json();
};

export interface StatsFullData {
  total_articles: number;
  last_24h: number;
  summarized_pct: number;
  uptime: string;
  db_size_mb: number;
  total_feeds: number;
  oldest_article: string;
  new_article?: string;
  newest_article?: string;
  by_source: { source: string; n: number }[];
  speed_leaderboard: { source: string; first_count: number }[];
  velocity: { t: string; n: number }[];
  by_category: { cat: string; n: number }[];
}

export const fetchStatsFull = async (): Promise<StatsFullData> => {
  const res = await fetch('/api/stats/full');
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export interface ClusterDetailData {
  cluster_id: string;
  articles: Article[];
  synthesis: string | null;
  perspectives: string[];
  tags: string[];
  topics: string[];
  related: {
    cluster_id: string;
    title: string;
    image_url: string | null;
  }[];
  total_reading_time: number;
}

export const fetchClusterDetail = async (clusterId: string): Promise<ClusterDetailData> => {
  const res = await fetch(`/api/cluster/${clusterId}`);
  if (!res.ok) throw new Error('Failed to fetch cluster detail');
  const json = await res.json();
  if (json.status === 'success') return json.data;
  throw new Error(json.message || 'Unknown error');
};

export const askAI = async (clusterId: string, query: string): Promise<string> => {
  const res = await fetch('/api/chat_cluster', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cluster_id: clusterId, query })
  });
  if (!res.ok) throw new Error('AI Chat failed');
  const data = await res.json();
  return data.response || 'No response';
};
