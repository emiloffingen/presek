import React, { useState, useEffect, useRef } from 'react';
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
      <h2 key={idx} className="text-xl font-bold text-primary mt-6 mb-2">
        {text}
      </h2>
    );
  }

  if (line.startsWith('**') && line.endsWith('**')) {
    return (
      <h3 key={idx} className="font-bold text-primary mt-4 mb-1">
        {line.slice(2, -2)}
      </h3>
    );
  }

  if (line.startsWith('- ') || line.startsWith('• ')) {
    return (
      <li key={idx} className="ml-4 text-secondary mb-1.5 text-base leading-relaxed">
        {line.substring(2)}
      </li>
    );
  }

  return (
    <p key={idx} className="text-secondary mb-3 text-base leading-relaxed">
      {line}
    </p>
  );
}

export const BriefingPage: React.FC = () => {
  const navigate = useNavigate();
  const [briefing, setBriefing] = useState<BriefingResponse | null>(() => window.__INITIAL_BRIEFING_DATA__);
  const [loading, setLoading] = useState(!briefing);
  const [error, setError] = useState<string | null>(null);
  const hydrated = useRef(!!briefing);

  useEffect(() => {
    if (hydrated.current) return;
    
    setLoading(true);
    apiClient.getBriefing()
      .then((data) => { setBriefing(data); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Грешка'))
      .finally(() => {
        setLoading(false);
        hydrated.current = true;
      });
  }, []);

  return (
    <div className="min-h-screen bg-primary">
      <Header />

      <div className="site-layout py-8">
        {/* Header Section */}
        <header className="mb-10 border-b-2 border-primary pb-8">
            <span className="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5 mb-4 inline-block">ДНЕВЕН ПРЕГЛЕД</span>
            <h1 className="font-serif text-3xl md:text-5xl font-bold leading-tight text-primary mb-4">
                Дневен Брифинг
            </h1>
            <div className="flex items-center gap-4 text-xs font-bold uppercase text-muted">
                {briefing && (
                  <span className="flex items-center gap-1">
                    <CalendarDays size={13} />
                    {new Date(briefing.date).toLocaleDateString('mk-MK', {
                      weekday: 'long',
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                )}
                <span>·</span>
                <span>АИ СИНТЕЗА</span>
            </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="lg:col-span-8">
            {loading && !briefing && (
              <div className="flex flex-col items-center gap-4 py-16">
                <Loader2 className="w-10 h-10 animate-spin text-accent" />
                <p className="text-muted">Вчитување преглед...</p>
              </div>
            )}

            {error && (
              <div className="bg-secondary p-10 text-center border-t-2 border-accent">
                <p className="text-accent font-bold uppercase tracking-widest">{error}</p>
                <button onClick={() => navigate('/')} className="mt-4 text-[10px] font-black uppercase text-primary hover:underline">Назад на почетна</button>
              </div>
            )}

            {!loading && !error && briefing && (
              <article className="reading-column">
                <div className="article-prose">
                  {briefing.content.split('\n').map((line, idx) => renderLine(line, idx))}
                </div>
              </article>
            )}

            {!loading && !error && !briefing && (
              <div className="bg-secondary p-10 text-center">
                <p className="text-4xl mb-3">📋</p>
                <p className="font-bold text-primary mb-1">Брифингот не е достапен</p>
                <p className="text-sm text-muted">Обидете се подоцна за денешниот преглед.</p>
              </div>
            )}
          </div>

          <aside className="lg:col-span-4 space-y-10">
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label">ЗОШТО БРИФИНГ?</h3>
                <p className="text-[11px] leading-relaxed text-muted italic">
                    Секое утро, нашиот АИ систем ги анализира најважните настани од стотици извори за да ви овозможи брз и објективен преглед на денот.
                </p>
            </div>
            
            <div className="rail-widget border-t-2 border-primary">
                <h3 className="rail-label flex items-center gap-2"><BookOpen size={14}/> ТЕМИ ВО ФОКУС</h3>
                <p className="text-[11px] leading-relaxed text-muted mb-4">
                    Прегледот ги опфаќа најважните вести од Македонија, Балканот и светот, синтетизирани за заштеда на вашето време.
                </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};
