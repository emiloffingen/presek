import { useEffect, useRef, useCallback } from 'react';

export const useSSE = <T,>(url: string, onUpdate: (data: T) => void) => {
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (typeof EventSource === 'undefined') {
      return;
    }

    eventSourceRef.current = new EventSource(url);

    // Listen for default 'message' event used in utils.py
    eventSourceRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onUpdate(data);
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    };

    eventSourceRef.current.onerror = () => {
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
