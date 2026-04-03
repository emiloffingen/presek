import { create } from 'zustand';
import { Cluster, TrendingItem } from '../types';
import * as api from '../api/client';

interface NewsState {
  clusters: Cluster[];
  trending: TrendingItem[];
  page: number;
  pageSize: number;
  hasMore: boolean;
  isFetching: boolean;
  topic: string;
  query: string;
  isSaved: boolean;
  
  // Actions
  setClusters: (clusters: Cluster[]) => void;
  appendClusters: (clusters: Cluster[]) => void;
  setTrending: (trending: TrendingItem[]) => void;
  setFilter: (filter: { topic?: string; query?: string; isSaved?: boolean }) => void;
  setPage: (page: number) => void;
  setHasMore: (hasMore: boolean) => void;
  setIsFetching: (isFetching: boolean) => void;
  fetchInitial: () => Promise<void>;
  fetchMore: () => Promise<void>;
  reset: () => void;
}

export const useNewsStore = create<NewsState>((set, get) => ({
  clusters: [],
  trending: [],
  page: 0,
  pageSize: 20,
  hasMore: true,
  isFetching: false,
  topic: '',
  query: '',
  isSaved: false,

  setClusters: (clusters) => set({ clusters }),
  appendClusters: (newClusters) => set((state) => ({ 
    clusters: [...state.clusters, ...newClusters] 
  })),
  setTrending: (trending) => set({ trending }),
  setFilter: (filter) => {
    const { topic, query, isSaved } = get();
    const changed = (filter.topic !== undefined && filter.topic !== topic) ||
                    (filter.query !== undefined && filter.query !== query) ||
                    (filter.isSaved !== undefined && filter.isSaved !== isSaved);
    
    set((state) => ({
      ...state,
      ...filter,
      clusters: changed ? [] : state.clusters,
      page: changed ? 0 : state.page,
      hasMore: changed ? true : state.hasMore
    }));
    
    if (changed) {
      get().fetchInitial();
    }
  },
  setPage: (page) => set({ page }),
  setHasMore: (hasMore) => set({ hasMore }),
  setIsFetching: (isFetching) => set({ isFetching }),
  
  fetchInitial: async () => {
    const { isFetching, topic, query, isSaved } = get();
    if (isFetching) return;
    
    set({ isFetching: true, page: 0, clusters: [] });
    try {
      const { data, has_more } = await api.fetchNews(0, topic, query, isSaved);
      set({ clusters: data, hasMore: has_more, isFetching: false });
    } catch (e) {
      console.error(e);
      set({ isFetching: false });
    }
  },
  
  fetchMore: async () => {
    const { isFetching, hasMore, page, topic, query, isSaved } = get();
    if (isFetching || !hasMore) return;
    
    set({ isFetching: true });
    try {
      const nextPage = page + 1;
      const { data, has_more } = await api.fetchNews(nextPage, topic, query, isSaved);
      set((state) => ({
        clusters: [...state.clusters, ...data],
        page: nextPage,
        hasMore: has_more,
        isFetching: false
      }));
    } catch (e) {
      console.error(e);
      set({ isFetching: false });
    }
  },

  reset: () => set({ clusters: [], page: 0, hasMore: true, isFetching: false }),
}));
