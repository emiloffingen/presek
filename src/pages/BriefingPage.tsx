import React, { useState, useEffect } from 'react';
import { Loader2, Calendar } from 'lucide-react';
import { apiClient } from '../api/client';
import { BriefingResponse } from '../types';

export const BriefingPage: React.FC = () => {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchBriefing = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getBriefing();
        setBriefing(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load briefing');
      } finally {
        setLoading(false);
      }
    };

    fetchBriefing();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">Вчитување преглед...</p>
          <Loader2 className="w-12 h-12 animate-spin mx-auto text-primary-600 dark:text-primary-400" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 text-lg mb-4">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-md sticky top-0 z-40 border-b dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <h1 className="text-3xl font-bold text-primary-600 dark:text-primary-400 inline-flex items-center gap-2">
            <Calendar className="w-8 h-8" />
            Дневен преглед
          </h1>
          {briefing && (
            <p className="text-gray-600 dark:text-gray-400">
              {new Date(briefing.date).toLocaleDateString('mk-MK', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
          )}
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {briefing ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 border dark:border-gray-700">
            <div className="prose prose-lg max-w-none dark:prose-invert">
              {briefing.content.split('\n').map((line, idx) => {
                if (line.startsWith('Ден ')) {
                  return (
                    <div key={idx} className="mt-6 mb-4">
                      <h2 className="text-xl font-bold text-primary-600 dark:text-primary-400">{line}</h2>
                    </div>
                  );
                }
                if (line.startsWith('- ')) {
                  return (
                    <li key={idx} className="ml-4 text-gray-700 dark:text-gray-300 mb-2">
                      {line.substring(2)}
                    </li>
                  );
                }
                if (line.trim() === '') {
                  return <div key={idx} className="my-2" />;
                }
                return (
                  <p key={idx} className="text-gray-700 dark:text-gray-300 mb-2">
                    {line}
                  </p>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center border dark:border-gray-700">
            <p className="text-gray-500 dark:text-gray-400 text-lg">Дневниот преглед не е достапен</p>
          </div>
        )}
      </div>
    </div>
  );
};
