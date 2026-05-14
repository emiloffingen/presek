import { apiBaseUrl } from '../lib/apiBase';

interface NewsResponse {
  status: 'success' | 'error';
  data: any[];
  page: number;
  page_size: number;
  has_more: boolean;
  total_clusters: number;
}

interface TrendingResponse {
  status: 'success' | 'error';
  words: Array<{ word: string; count: number; trend: string }>;
}

interface StatsResponse {
  status: 'success' | 'error';
  total_articles: number;
  last_24h: number;
  summarized_pct: number;
}

export async function fetchNews(page: number, topic: string, query: string, forceRefresh: boolean): Promise<NewsResponse> {
  const url = new URL(`${apiBaseUrl()}/news`);
  const params = new URLSearchParams();
  
  if (page > 0) params.append('page', page.toString());
  if (topic) params.append('topic', topic);
  if (query) params.append('q', query);
  if (forceRefresh) params.append('force_refresh', 'true');
  
  url.search = params.toString();
  
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error('Failed to fetch news');
  }
  
  return await response.json();
}

export async function fetchTrending(): Promise<Array<{ word: string; count: number; trend: string }>> {
  const response = await fetch(`${apiBaseUrl()}/trending`);
  if (!response.ok) {
    throw new Error('Failed to fetch trending');
  }
  
  const data = await response.json();
  return Array.isArray(data) ? data : data.words || [];
}

export async function fetchStatsFull(): Promise<StatsResponse> {
  const response = await fetch(`${apiBaseUrl()}/stats/full`);
  if (!response.ok) {
    throw new Error('Failed to fetch stats');
  }
  
  return await response.json();
}