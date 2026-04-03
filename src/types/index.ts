export interface Article {
  id: number;
  source: string;
  title: string;
  description: string | null;
  link: string;
  image_url: string | null;
  created_at: string;
  cluster_id: string;
  summary: string | null;
  country: string;
  category: string;
  clicks: number;
  sentiment: string | null;
}

export interface Cluster {
  cluster_id: string;
  articles: Article[];
  score: number;
  is_breaking: boolean;
  has_balanced: boolean;
  representative_image: string | null;
}

export interface TrendingItem {
  word: string;
  count: number;
  sentiment: string;
}

export interface WeatherData {
  temp: number | null;
  icon: string;
  aqi: number | null;
}
