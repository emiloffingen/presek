import { useEffect, useRef, useCallback } from 'react';

interface SSEUpdate {
  cluster_id: string;
  new_articles: number;
}

export const useSSE = (url: string, onUpdate: (data: SSEUpdate) => void) => {
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (typeof EventSource === 'undefined') {
      console.warn('Server-Sent Events not supported');
      return;
    }

    eventSourceRef.current = new EventSource(url);

    eventSourceRef.current.addEventListener('update', (event) => {
      try {
        const data = JSON.parse(event.data);
        onUpdate(data);
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    });

    eventSourceRef.current.onerror = () => {
      console.error('SSE connection error');
      disconnect();
    };
  }, [url, onUpdate]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { disconnect };
};
