import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { TrendingWord } from '../types';

export const TrendingSidebar: React.FC = () => {
  const [trending, setTrending] = useState<TrendingWord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTrending = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getTrending();
        setTrending(data);
      } catch (error) {
        console.error('Failed to fetch trending:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTrending();
    const interval = setInterval(fetchTrending, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-4">
        <h3 className="font-bold text-lg mb-4">🔥 Тренд</h3>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-6 bg-gray-200 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-4 sticky top-4">
      <h3 className="font-bold text-lg mb-4">🔥 Тренд</h3>
      <div className="space-y-3">
        {trending.slice(0, 10).map((word, idx) => (
          <div
            key={idx}
            className="flex justify-between items-center p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer transition"
          >
            <div className="flex-1">
              <p className="font-semibold text-sm">{word.word}</p>
              <p className="text-xs text-gray-500">{word.count} споменувања</p>
            </div>
            <span className="text-lg">{word.trend}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
