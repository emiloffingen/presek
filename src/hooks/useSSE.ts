import { useEffect } from 'react';
import { useNewsStore } from '@/store/useNewsStore';

export const useSSE = () => {
  const { appendClusters } = useNewsStore();

  useEffect(() => {
    if (!window.EventSource) return;

    const source = new EventSource('/api/live');

    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'new_clusters') {
          // If we want to automatically add new clusters to the top
          // We could prepend them, but for now let's just show a notification
          // or we could use useNewsStore to add them.
          console.log('New clusters available:', data.count);
        }
      } catch (err) {
        console.error('SSE error parsing message:', err);
      }
    };

    source.onerror = () => {
      console.warn('SSE connection closed, reconnecting...');
      source.close();
    };

    return () => {
      source.close();
    };
  }, [appendClusters]);
};
