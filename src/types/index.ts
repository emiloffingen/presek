export interface Article {
  id: number;
  cluster_id: string;
  title: string;
  description: string;
  source: string;
  link: string;
  country: string;
  category: string;
  topic: string;
  created_at: string;
  image_url: string | null;
  clicks: number;
  reading_time: number;
  summary?: string;
  is_translated: number;
  is_fact_check?: boolean;
}

export interface ClusterSummary {
  angle: string;
  content: string;
}

export interface TimelineEntry {
  article_id: number;
  title: string;
  source: string;
  created_at: string;
  is_first: boolean;
  is_major: boolean;
}

export interface SentimentData {
  score: number;
  label: string;
  tone_analysis?: {
    sensationalism: number;
    objectivity: number;
    emotional_charge: number;
  };
}

export interface NewsCluster {
  cluster_id: string;
  articles: Article[];
  representative_image: string | null;
  score: number;
  is_breaking: boolean;
  has_synthesis: boolean;
  has_balanced: boolean;
  has_fact_check: boolean;
  reading_time: number;
}

export interface ClusterDetail extends NewsCluster {
  synthesis: string;
  generated_article: string | null;
  sentiment: SentimentData | null;
  timeline: TimelineEntry[];
  perspectives: ClusterSummary[];
  tags: string[];
  topics: string[];
  related: Array<{
    cluster_id: string;
    title: string;
    image_url: string | null;
    tags?: string[];
  }>;
  total_reading_time: number;
}

export interface NewsResponse {
  status: 'success' | 'error';
  page: number;
  page_size: number;
  clusters: NewsCluster[];
  has_more: boolean;
  total_clusters: number;
  message?: string;
}

export interface TrendingWord {
  word: string;
  count: number;
  trend: string; // '↑', '↓', '→'
}

export interface Stats {
  total_articles: number;
  by_category: Array<{ category: string; n: number }>;
  by_source: Array<{ source: string; n: number }>;
  last_24h: number;
  summarized: number;
}

export interface FullStats extends Stats {
  uptime: string;
  db_size_mb: number;
  total_feeds: number;
  oldest_article: string;
  new_article: string;
  velocity: Array<{ t: string; n: number }>;
  speed_leaderboard: Array<{ source: string; first_count: number }>;
  summarized_pct: number;
}

export interface Weather {
  temp: number;
  icon: string;
  aqi: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  database: {
    ok: boolean;
    article_count: number;
    size_mb: number;
    error?: string;
  };
  redis: {
    ok: boolean;
    url: string;
    error?: string;
  };
}

export interface BriefingResponse {
  date: string;
  content: string;
}

export interface ChatResponse {
  status: 'success' | 'error';
  response: string;
}
