import React, { useEffect, useState } from 'react';
import { useNewsStore } from '@/store/useNewsStore';

export const PulseTicker: React.FC = () => {
  const [entities, setEntities] = useState<any[]>([]);

  useEffect(() => {
    const fetchPulse = async () => {
      try {
        const res = await fetch('/api/trending');
        if (!res.ok) return;
        const data = await res.json();
        // Duplicate for seamless scroll
        setEntities([...data, ...data]);
      } catch (e) {}
    };
    fetchPulse();
    const interval = setInterval(fetchPulse, 600000); // 10 mins
    return () => clearInterval(interval);
  }, []);

  if (entities.length === 0) {
    return <span className="ticker-item">LOADING SYSTEM...</span>;
  }

  return (
    <>
      {entities.map((e, i) => (
        <a key={i} href={`/?q=${encodeURIComponent(e.word)}`} className="ticker-item">
          #{e.word} <span className="val">{e.count}</span>
        </a>
      ))}
    </>
  );
};
