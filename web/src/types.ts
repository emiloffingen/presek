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
  source_signal?: {
    trust_label?: string;
    role_label?: string;
    trust_level?: number;
  };
  is_fact_check?: boolean;
  image_caption?: string;
}

export interface ClusterSummary {
  angle: string;
  content: string;
}

export interface NewsCluster {
  cluster_id: string;
  articles: Article[];
  representative_image: string | null;
  score: number;
  is_breaking: boolean;
  has_synthesis: boolean;
  has_balanced: boolean;
  reading_time: number;
  reason?: string;
  entities?: string[];
  homepage_score?: number;
}

export interface ClusterDetail extends NewsCluster {
  synthesis: string;
  generated_article?: string;
  perspectives: ClusterSummary[];
  sentiment?: any;
  verification_report?: any;
  ai_summary_bullets?: string[];
  synthesis_updated_at?: string;
  synthesis_freshness?: {
    is_stale: boolean;
    new_article_count: number;
    reasons: string[];
  };
  tags: string[];
  topics: string[];
  related: Array<{
    cluster_id: string;
    title: string;
    image_url: string | null;
    tags?: string[];
    relationship_label?: string;
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

export interface AskPresekCitation {
  source?: string;
  title?: string;
  link?: string;
  snippet?: string;
  created_at?: string;
}

export interface AskPresekResponse {
  status: 'success' | 'error';
  answer: string;
  response?: string;
  confidence?: 'high' | 'medium' | 'low' | string;
  confirmed_points?: string[];
  unclear_points?: string[];
  source_differences?: string;
  citations?: AskPresekCitation[];
  related_questions?: string[];
}
