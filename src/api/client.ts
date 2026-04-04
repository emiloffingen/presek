import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  NewsResponse,
  TrendingWord,
  Stats,
  FullStats,
  Weather,
  HealthResponse,
  BriefingResponse,
  ClusterDetail,
  ChatResponse,
} from '../types';

class ApiClient {
  private client: AxiosInstance;
  private baseURL: string;

  constructor() {
    this.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 429) {
          console.warn('Rate limited. Please wait before making more requests.');
        }
        return Promise.reject(error);
      }
    );
  }

  async getNews(params: {
    country?: string;
    page?: number;
    page_size?: number;
    category?: string;
    topic?: string;
    q?: string;
    sort?: 'recent' | 'popular';
    follow_sources?: string;
    follow_topics?: string;
  }, config?: import('axios').AxiosRequestConfig): Promise<NewsResponse> {
    try {
      const response = await this.client.get<NewsResponse>('/api/news', { 
        ...config,
        params 
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getClusterDetail(clusterId: string): Promise<{ status: string; data: ClusterDetail }> {
    try {
      const response = await this.client.get(`/api/cluster/${clusterId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getTrending(): Promise<TrendingWord[]> {
    try {
      const response = await this.client.get<TrendingWord[]>('/api/trending');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getSources(): Promise<any[]> {
    try {
      const response = await this.client.get<any[]>('/api/sources');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getArchive(params: { date: string; page: number; page_size: number }): Promise<any> {
    try {
      const response = await this.client.get('/api/archive', { params });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getStats(): Promise<{ status: string; data: Stats }> {
    try {
      const response = await this.client.get('/api/stats');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getFullStats(): Promise<FullStats> {
    try {
      const response = await this.client.get<FullStats>('/api/stats/full');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getPulse(): Promise<Array<{ source: string; count: number }>> {
    try {
      const response = await this.client.get('/api/sources/pulse');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getWeather(): Promise<Weather> {
    try {
      const response = await this.client.get<Weather>('/api/weather');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getBriefing(): Promise<BriefingResponse> {
    try {
      const response = await this.client.get<BriefingResponse>('/api/briefing');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getHealth(): Promise<HealthResponse> {
    try {
      const response = await this.client.get<HealthResponse>('/api/health');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async chatCluster(clusterId: string, query: string): Promise<ChatResponse> {
    try {
      const response = await this.client.post<ChatResponse>('/api/chat_cluster', {
        cluster_id: clusterId,
        query,
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  getImageUrl(url: string | null, width: number = 600): string {
    if (!url) return '';
    if (url.startsWith('/')) return url;
    return `/proxy?url=${encodeURIComponent(url)}&w=${width}`;
  }

  private handleError(error: unknown): Error {
    if (axios.isAxiosError(error)) {
      if (error.response?.data?.message) {
        return new Error(error.response.data.message);
      }
      return new Error(error.message || 'API request failed');
    }
    return error instanceof Error ? error : new Error('Unknown error');
  }
}

export const apiClient = new ApiClient();
