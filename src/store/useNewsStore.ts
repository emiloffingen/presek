import { create } from 'zustand';
import { NewsCluster, FullStats } from '../types';

interface NewsStore {
  clusters: NewsCluster[];
  isLoading: boolean;
  error: string | null;
  page: number;
  pageSize: number;
  hasMore: boolean;
  totalClusters: number;

  setClusters: (clusters: NewsCluster[]) => void;
  addClusters: (clusters: NewsCluster[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  setHasMore: (hasMore: boolean) => void;
  setTotalClusters: (total: number) => void;
  reset: () => void;
}

export const useNewsStore = create<NewsStore>((set) => ({
  clusters: [],
  isLoading: false,
  error: null,
  page: 0,
  pageSize: 50,
  hasMore: true,
  totalClusters: 0,

  setClusters: (clusters) => set({ clusters }),
  addClusters: (clusters) => set((state) => ({ clusters: [...state.clusters, ...clusters] })),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  setPage: (page) => set({ page }),
  setPageSize: (size) => set({ pageSize: size }),
  setHasMore: (hasMore) => set({ hasMore }),
  setTotalClusters: (total) => set({ totalClusters: total }),
  reset: () =>
    set({
      clusters: [],
      isLoading: false,
      error: null,
      page: 0,
      hasMore: true,
    }),
}));

interface UIStore {
  sidebarOpen: boolean;
  selectedCategory: string;
  selectedTopic: string;
  searchQuery: string;
  stats: FullStats | null;
  userInterests: Record<string, number>;
  followedSources: Set<string>;
  recentlyRead: string[];

  setSidebarOpen: (open: boolean) => void;
  setSelectedCategory: (category: string) => void;
  setSelectedTopic: (topic: string) => void;
  setSearchQuery: (query: string) => void;
  setStats: (stats: FullStats | null) => void;
  trackInterest: (key: string) => void;
  toggleSource: (source: string) => void;
  addRecentRead: (clusterId: string) => void;
  getTopInterests: () => string[];
}

// ── Saved Articles ─────────────────────────────────────────────
interface SavedStore {
  savedIds: Set<string>;
  toggle: (id: string) => void;
  isSaved: (id: string) => boolean;
}

const _loadSaved = (): Set<string> => {
  try {
    const raw = localStorage.getItem('presek:saved');
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
};

const _persistSaved = (ids: Set<string>) => {
  try {
    localStorage.setItem('presek:saved', JSON.stringify([...ids]));
  } catch {}
};

export const useSavedStore = create<SavedStore>((set, get) => ({
  savedIds: _loadSaved(),
  toggle: (id) =>
    set((state) => {
      const next = new Set(state.savedIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      _persistSaved(next);
      return { savedIds: next };
    }),
  isSaved: (id) => get().savedIds.has(id),
}));

const _loadInterests = (): Record<string, number> => {
  try {
    const raw = localStorage.getItem('presek:interests');
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};

const _loadSources = (): Set<string> => {
  try {
    const raw = localStorage.getItem('presek:sources');
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
};

const _loadRecent = (): string[] => {
  try {
    const raw = localStorage.getItem('presek:recent');
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

export const useUIStore = create<UIStore>((set, get) => ({
  sidebarOpen: true,
  selectedCategory: 'Македонија',
  selectedTopic: '',
  searchQuery: '',
  stats: null,
  userInterests: _loadInterests(),
  followedSources: _loadSources(),
  recentlyRead: _loadRecent(),

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSelectedCategory: (category) => set({ selectedCategory: category }),
  setSelectedTopic: (topic) => set({ selectedTopic: topic }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setStats: (stats) => set({ stats }),
  trackInterest: (key) => {
    if (!key || key === 'Македонија' || key === 'Сите') return;
    set((state) => {
      const next = { ...state.userInterests, [key]: (state.userInterests[key] || 0) + 1 };
      localStorage.setItem('presek:interests', JSON.stringify(next));
      return { userInterests: next };
    });
  },
  toggleSource: (source) => set(state => {
    const next = new Set(state.followedSources);
    if (next.has(source)) next.delete(source);
    else next.add(source);
    localStorage.setItem('presek:sources', JSON.stringify([...next]));
    return { followedSources: next };
  }),
  addRecentRead: (clusterId) => set(state => {
    const next = [clusterId, ...state.recentlyRead.filter(id => id !== clusterId)].slice(0, 20);
    localStorage.setItem('presek:recent', JSON.stringify(next));
    return { recentlyRead: next };
  }),
  getTopInterests: () => {
    const interests = get().userInterests;
    return Object.entries(interests)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([key]) => key);
  }
}));
