import React, { useEffect, useMemo, useState } from 'react';
import { Clock3, Sparkles } from 'lucide-react';
import {
  normalizeBriefingPayload,
  scrubBriefingBoilerplate,
  simplifyBriefingBullet,
} from '../../utils/briefingCopy';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { briefing } from '../../i18n/namespaces/briefing';

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

function readModeFromUrl(fallback: 'quick' | 'full' = 'quick'): 'quick' | 'full' {
  if (typeof window === 'undefined') return fallback;
  const params = new URLSearchParams(window.location.search);
  return params.get('mode') === 'full' ? 'full' : 'quick';
}

export default function BriefingQuickRead({
  lang = 'sr',
  quickRead,
  narratives = [],
  initialMode = 'quick',
}: Props) {
  const t = useClientTranslations(lang, briefing);
  const [mode, setMode] = useState<'quick' | 'full'>(() => readModeFromUrl(initialMode));

  const mergedNarratives = useMemo(() => {
    const fromQuick = quickRead?.narratives || [];
    const source = fromQuick.length ? fromQuick : narratives;
    return normalizeBriefingPayload(source, lang)
      .map((item) => ({
        ...item,
        text: scrubBriefingBoilerplate(item.text, lang),
      }))
      .filter((item) => item.text.length > 0);
  }, [quickRead, narratives, lang]);

  const cleanQuickRead = useMemo(() => normalizeBriefingPayload(quickRead, lang), [quickRead, lang]);

  const simplifiedBullets = useMemo(() => {
    const bullets = cleanQuickRead?.bullets || [];
    return bullets
      .map((bullet: string) => simplifyBriefingBullet(bullet, lang))
      .filter(Boolean);
  }, [cleanQuickRead, lang]);

  useEffect(() => {
    document.documentElement.dataset.briefingMode = mode;
    const main = document.querySelector('main[data-briefing-mode]');
    if (main instanceof HTMLElement) {
      main.dataset.briefingMode = mode;
    }
    return () => {
      delete document.documentElement.dataset.briefingMode;
    };
  }, [mode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (mode === 'full') {
      params.set('mode', 'full');
    } else {
      params.delete('mode');
    }
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
    window.history.replaceState({}, '', nextUrl);
  }, [mode]);

  const readMinutes = cleanQuickRead?.read_minutes || 5;
  const stats = cleanQuickRead?.stats || {};
  const showBullets = simplifiedBullets.length > 0 && mergedNarratives.length === 0;

  return (
    <div className="briefing-edition-shell">
      <div className="briefing-edition-switch" role="tablist" aria-label={t('briefing.mode_reading_label')}>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'quick'}
          className={`briefing-edition-link ${mode === 'quick' ? 'is-active' : ''}`}
          onClick={() => setMode('quick')}
        >
          <span className="briefing-edition-link__label">{t('briefing.mode_quick')}</span>
          <span className="briefing-edition-link__hint">{readMinutes} {t('briefing.min_short')}</span>
        </button>
        <span className="briefing-edition-sep" aria-hidden="true">·</span>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'full'}
          className={`briefing-edition-link ${mode === 'full' ? 'is-active' : ''}`}
          onClick={() => setMode('full')}
        >
          <span className="briefing-edition-link__label">{t('briefing.mode_full')}</span>
          <span className="briefing-edition-link__hint">{t('briefing.mode_full_hint')}</span>
        </button>
      </div>

      <section
        className={`briefing-quick-panel ${mode === 'quick' ? 'is-visible' : ''}`}
        aria-label={cleanQuickRead.subline || cleanQuickRead.headline}
      >
        <div className="briefing-quick-head">
          <div>
            <p className="briefing-quick-kicker">
              <Sparkles size={14} />
              <span>
                {readMinutes} {t('briefing.min_short')} · {t('briefing.main_themes')}
              </span>
            </p>
            <h2 className="briefing-quick-title">{cleanQuickRead.subline}</h2>
          </div>
          <div className="briefing-quick-time">
            <Clock3 size={15} />
            <span>{readMinutes} {t('briefing.min_short')}</span>
          </div>
        </div>

        {mergedNarratives.length > 0 && (
          <div className="briefing-quick-narratives">
            {mergedNarratives.slice(0, 4).map((item, index) => (
              <blockquote key={`${index}-${item.text.slice(0, 24)}`}>{item.text}</blockquote>
            ))}
          </div>
        )}

        {showBullets && (
          <ul className="briefing-quick-bullets">
            {simplifiedBullets.map((bullet: string) => (
              <li key={bullet.slice(0, 48)}>{bullet}</li>
            ))}
          </ul>
        )}

        <div className="briefing-quick-stats">
          {stats.total_articles != null && (
            <span>{stats.total_articles} {t('briefing.reports')}</span>
          )}
          {stats.pluralism_score != null && (
            <span>{stats.pluralism_score}% {t('briefing.pluralism')}</span>
          )}
          {stats.intl_share != null && (
            <span>{stats.intl_share}% {t('briefing.international')}</span>
          )}
        </div>
      </section>
    </div>
  );
}
