import axios from 'axios';
import type { AxiosInstance, AxiosError, AxiosResponse } from 'axios';
import type {
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
    // Determine the API base URL
    if (typeof window !== 'undefined') {
      // Client-side
      let url = import.meta.env.PUBLIC_API_URL || '/api';
      
      // Safeguard: If the build environment leaked a localhost URL to a production site
      if (url.includes('localhost') && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        url = '/api';
      }
      
      this.baseURL = url;
    } else {
      // Server-side (SSR)
      this.baseURL = import.meta.env.PUBLIC_API_URL || 'http://127.0.0.1:5001/api';
    }
    
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 15000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.response.use(
      (response: AxiosResponse) => response,
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
  }, config?: any): Promise<NewsResponse> {
    try {
      const response = await this.client.get<NewsResponse>('/news', { 
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
      const response = await this.client.get(`/cluster/${clusterId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getTrending(): Promise<TrendingWord[]> {
    try {
      const response = await this.client.get<TrendingWord[]>('/trending');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getSources(): Promise<any[]> {
    try {
      const response = await this.client.get<any[]>('/sources');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getArchive(params: { date: string; page: number; page_size: number }): Promise<any> {
    try {
      const response = await this.client.get('/archive', { params });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getStats(): Promise<{ status: string; data: Stats }> {
    try {
      const response = await this.client.get('/stats');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getFullStats(): Promise<FullStats> {
    try {
      const response = await this.client.get<FullStats>('/stats/full');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getPulse(): Promise<Array<{ source: string; count: number }>> {
    try {
      const response = await this.client.get('/sources/pulse');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getWeather(): Promise<Weather> {
    try {
      const response = await this.client.get<Weather>('/weather');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getBriefing(): Promise<BriefingResponse> {
    try {
      const response = await this.client.get<BriefingResponse>('/briefing');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getHealth(): Promise<HealthResponse> {
    try {
      const response = await this.client.get<HealthResponse>('/health');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async chatCluster(clusterId: string, query: string): Promise<ChatResponse> {
    try {
      const response = await this.client.post<ChatResponse>('/chat_cluster', {
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
      const axiosError = error as AxiosError<any>;
      if (axiosError.response?.data?.message) {
        return new Error(axiosError.response.data.message);
      }
      return new Error(axiosError.message || 'API request failed');
    }
    return error instanceof Error ? error : new Error('Unknown error');
  }
}

export const apiClient = new ApiClient();
