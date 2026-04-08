import { useEffect, useRef } from 'react';

export const useSSE = <T,>(url: string, onUpdate: (data: T) => void) => {
  // Keep the callback in a ref so a fresh closure on each render
  // doesn't tear down and reopen the EventSource.
  const onUpdateRef = useRef(onUpdate);
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    if (typeof EventSource === 'undefined') return;

    const es = new EventSource(url);
    es.onmessage = (event) => {
      try {
        onUpdateRef.current(JSON.parse(event.data));
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    };
    es.onerror = () => es.close();

    return () => es.close();
  }, [url]);
};
