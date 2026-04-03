import React, { useState, useEffect } from 'react';
import { BookOpen, Loader2, CalendarDays, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { BriefingResponse } from '../types';
import { Header } from '../components/Header';

function renderLine(line: string, idx: number) {
  if (line.trim() === '') return <div key={idx} className="my-2" />;

  if (/^#{1,3}\s/.test(line)) {
    const text = line.replace(/^#{1,3}\s/, '');
    return (
      <h2 key={idx} className="text-xl font-bold text-ink dark:text-white mt-6 mb-2">
        {text}
      </h2>
    );
  }

  if (line.startsWith('**') && line.endsWith('**')) {
    return (
      <h3 key={idx} className="font-bold text-ink dark:text-slate-100 mt-4 mb-1">
        {line.slice(2, -2)}
      </h3>
    );
  }

  if (line.startsWith('- ') || line.startsWith('• ')) {
    return (
      <li key={idx} className="ml-4 text-ink dark:text-slate-300 mb-1.5 text-base leading-relaxed">
        {line.substring(2)}
      </li>
    );
  }

  return (
    <p key={idx} className="text-ink dark:text-slate-300 mb-3 text-base leading-relaxed">
      {line}
    </p>
  );
}

export const BriefingPage: React.FC = () => {
  const navigate = useNavigate();
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getBriefing()
      .then((data) => { setBriefing(data); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Грешка'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-surface-1 dark:bg-dark-0">
      <Header />

      <div className="page-container py-8 max-w-3xl">
        {/* Page title */}
        <div className="mb-6">
          <button onClick={() => navigate(-1)} className="btn-ghost text-sm mb-4">
            <ArrowLeft size={16} />
            Назад
          </button>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <BookOpen size={20} className="text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-ink dark:text-white">Дневен преглед</h1>
              {briefing && (
                <p className="text-sm text-ink-muted dark:text-slate-400 flex items-center gap-1">
                  <CalendarDays size={13} />
                  {new Date(briefing.date).toLocaleDateString('mk-MK', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              )}
            </div>
          </div>
        </div>

        {loading && (
          <div className="flex flex-col items-center gap-4 py-16">
            <Loader2 className="w-10 h-10 animate-spin text-brand-600" />
            <p className="text-ink-muted dark:text-slate-400">Вчитување преглед...</p>
          </div>
        )}

        {error && (
          <div className="card p-6 text-center">
            <p className="text-brand-600 dark:text-brand-400">{error}</p>
          </div>
        )}

        {!loading && !error && briefing && (
          <article className="card p-6 md:p-8">
            <div className="article-prose">
              {briefing.content.split('\n').map((line, idx) => renderLine(line, idx))}
            </div>
          </article>
        )}

        {!loading && !error && !briefing && (
          <div className="card p-10 text-center">
            <p className="text-4xl mb-3">📋</p>
            <p className="font-semibold text-ink dark:text-slate-200 mb-1">Прегледот не е достапен</p>
            <p className="text-sm text-ink-muted dark:text-slate-500">Обидете се подоцна</p>
          </div>
        )}
      </div>
    </div>
  );
};
