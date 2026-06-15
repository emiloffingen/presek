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
  ingested_at?: string;
  image_url: string | null;
  clicks: number;
  credibility?: number;
  reading_time: number;
  summary?: string;
  full_content?: string;
  is_translated: number;
  source_signal?: {
    trust_label?: string;
    role_label?: string;
    trust_level?: number;
    role_tone?: string;
  };
  is_breaking?: boolean;
  is_fact_check?: boolean;
  image_caption?: string;
  is_global?: boolean;
  is_redundant?: boolean;
  coverage_balance?: {
    score: number;
    label: string | null;
  };
}

export interface ClusterSummary {
  angle: string;
  content: string;
}

export interface CitationSource {
  index: number;
  source: string;
  title: string;
  link: string;
  created_at?: string;
  category?: string;
}

export interface NewsCluster {
  cluster_id: string;
  articles: Article[];
  representative_image: string | null;
  dominant_color?: string | null;
  synthetic_headline?: string | null;
  synthetic_standfirst?: string | null;
  score: number;
  is_breaking: boolean;
  has_synthesis: boolean;
  has_audio?: boolean;
  audio_url?: string | null;
  has_balanced: boolean;
  has_fact_check?: boolean;
  reading_time: number;
  reason?: string;
  entities?: string[];
  analyst_entities?: string[];
  key_facts?: string[];
  pulse_score?: number;
  pluralism_score?: number;
  homepage_score?: number;
  importance_score?: number;
  created_at?: string;
  display_name?: string;
  tags?: string[];
  topics?: string[];
  synthesis_updated_at?: string | null;
  synthesis_freshness?: {
    is_stale?: boolean;
    new_article_count?: number;
    latest_article_at?: string | null;
    synthesis_updated_at?: string | null;
  };
  synthesis_meta?: {
    generation_provider?: string | null;
    generation_model?: string | null;
    quality_score?: number | null;
    fallback_reason?: string | null;
    is_provisional?: boolean;
    needs_upgrade?: boolean;
  };
}

export interface ClusterDetail extends NewsCluster {
  synthesis: string;
  generated_article?: string;
  synthetic_headline?: string | null;
  synthetic_standfirst?: string | null;
  perspectives: ClusterSummary[];
  sentiment?: any;
  tone_analysis?: any;
  verification_report?: any;
  trust_summary?: {
    score: number;
    tier: string;
    label: string;
    detail: string;
    sources_count: number;
    pluralism_score?: number | null;
    is_stale?: boolean;
    has_verification?: boolean;
    is_provisional?: boolean;
    needs_upgrade?: boolean;
  };
  cross_lingual_counterparts?: Array<{
    cluster_id: string;
    lang: string;
    headline: string;
    storyline_title?: string;
    relevance_score?: number;
  }>;
  ai_summary_bullets?: string[];
  citation_sources?: CitationSource[];
  synthesis_updated_at?: string;
  synthesis_freshness?: {
    is_stale: boolean;
    new_article_count: number;
    reasons: string[];
  };
  synthesis_meta?: {
    generation_provider?: string | null;
    generation_model?: string | null;
    quality_score?: number | null;
    fallback_reason?: string | null;
    is_provisional?: boolean;
    needs_upgrade?: boolean;
  };
  tags: string[];
  topics: string[];
  related: Array<{
    cluster_id: string;
    title: string;
    image_url: string | null;
    source?: string;
    created_at?: string;
    tags?: string[];
    relationship_label?: string;
    relationship_note?: string;
    shared_tags?: string[];
    shared_topics?: string[];
    shared_entities?: string[];
  }>;
  timeline?: Array<{
    article_id: number;
    title: string;
    source: string;
    created_at: string;
    is_first: boolean;
    is_major: boolean;
    milestone: string;
  }>;
  total_reading_time: number;
  narrative_diversity?: {
    verdict?: string;
  };
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

export interface HomeResponse {
  status: 'success' | 'error';
  news: NewsCluster[];
  recent: NewsCluster[];
  trending: string[];
  top_entities: Array<{ name: string; display_name: string; count: number }>;
  stats: any;
  latest_wire: Article[];
}

export interface BriefingResponse {
  date: string;
  content: string;
}

export interface ChatResponse {
  status: 'success' | 'error';
  response: string;
}
