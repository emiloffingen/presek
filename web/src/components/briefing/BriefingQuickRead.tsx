import React, { useEffect, useMemo, useState } from 'react';
import { Clock3, BookOpen, Sparkles } from 'lucide-react';

type Narrative = {
  text: string;
  sentiment?: string;
};

type QuickRead = {
  headline: string;
  subline: string;
  read_minutes: number;
  bullets: string[];
  narratives?: Narrative[];
  stats?: {
    total_articles?: number | null;
    intl_share?: number | null;
    pluralism_score?: number | null;
  };
};

type Props = {
  lang?: 'sr' | 'mk';
  quickRead: QuickRead;
  narratives?: Narrative[];
  initialMode?: 'quick' | 'full';
};

function readModeFromUrl(fallback: 'quick' | 'full' = 'full'): 'quick' | 'full' {
  if (typeof window === 'undefined') return fallback;
  const params = new URLSearchParams(window.location.search);
  return params.get('mode') === 'quick' ? 'quick' : 'full';
}

export default function BriefingQuickRead({
  lang = 'sr',
  quickRead,
  narratives = [],
  initialMode = 'full',
}: Props) {
  const isMK = lang === 'mk';
  const [mode, setMode] = useState<'quick' | 'full'>(() => readModeFromUrl(initialMode));

  const mergedNarratives = useMemo(() => {
    const fromQuick = quickRead?.narratives || [];
    return fromQuick.length ? fromQuick : narratives;
  }, [quickRead, narratives]);

  useEffect(() => {
    document.documentElement.dataset.briefingMode = mode;
    return () => {
      delete document.documentElement.dataset.briefingMode;
    };
  }, [mode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (mode === 'quick') {
      params.set('mode', 'quick');
    } else {
      params.delete('mode');
    }
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
    window.history.replaceState({}, '', nextUrl);
  }, [mode]);

  const quickLabel = isMK ? '5 мин' : '5 min';
  const fullLabel = isMK ? 'Целосно' : 'Celosno';
  const stats = quickRead?.stats || {};

  return (
    <>
      <section className={`briefing-quick-panel ${mode === 'quick' ? 'is-visible' : ''}`} aria-label={quickRead.headline}>
        <div className="briefing-quick-head">
          <div>
            <p className="briefing-quick-kicker">
              <Sparkles size={14} />
              <span>{quickRead.headline}</span>
            </p>
            <h2 className="briefing-quick-title">{quickRead.subline}</h2>
          </div>
          <div className="briefing-quick-time">
            <Clock3 size={15} />
            <span>{quickRead.read_minutes} min</span>
          </div>
        </div>

        {mergedNarratives.length > 0 && (
          <div className="briefing-quick-narratives">
            {mergedNarratives.slice(0, 3).map((item, index) => (
              <blockquote key={`${index}-${item.text.slice(0, 24)}`}>{item.text}</blockquote>
            ))}
          </div>
        )}

        {quickRead.bullets?.length > 0 && (
          <ul className="briefing-quick-bullets">
            {quickRead.bullets.map((bullet) => (
              <li key={bullet.slice(0, 40)}>{bullet}</li>
            ))}
          </ul>
        )}

        <div className="briefing-quick-stats">
          {stats.total_articles != null && (
            <span>{stats.total_articles} {isMK ? 'извештаи' : 'izveštaja'}</span>
          )}
          {stats.pluralism_score != null && (
            <span>{stats.pluralism_score}% {isMK ? 'плурализам' : 'pluralizam'}</span>
          )}
          {stats.intl_share != null && (
            <span>{stats.intl_share}% {isMK ? 'интернационално' : 'internacionalno'}</span>
          )}
        </div>
      </section>

      <div className="briefing-mode-bar">
        <button
          type="button"
          className={`briefing-mode-btn ${mode === 'quick' ? 'is-active' : ''}`}
          onClick={() => setMode('quick')}
        >
          <Clock3 size={14} />
          <span>{quickLabel}</span>
        </button>
        <button
          type="button"
          className={`briefing-mode-btn ${mode === 'full' ? 'is-active' : ''}`}
          onClick={() => setMode('full')}
        >
          <BookOpen size={14} />
          <span>{fullLabel}</span>
        </button>
      </div>
    </>
  );
}
