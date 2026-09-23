import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { applyReadingMode, saveReadingMode } from '../../lib/readingMode';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { settings } from '../../i18n/namespaces/settings';

export default function ZenReadingContext({
  headline,
  lang = 'mk',
}: {
  headline: string;
  lang?: string;
}) {
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const sync = () => {
      setVisible(document.body.classList.contains('zen-mode'));
    };
    sync();
    window.addEventListener('presek:reading-mode-changed', sync);
    document.addEventListener('astro:page-load', sync);
    return () => {
      window.removeEventListener('presek:reading-mode-changed', sync);
      document.removeEventListener('astro:page-load', sync);
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const pct = max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0;
      setProgress(Math.round(pct));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, [visible]);

  if (!visible) return null;

  const exitFocus = () => {
    saveReadingMode('standard');
    applyReadingMode('standard');
  };

  return (
    <div className="zen-reading-context" role="status">
      <div className="zen-reading-context-progress" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="zen-reading-context-body">
        <span className="zen-reading-context-kicker">{t('reading.focus_mode')}</span>
        <p className="zen-reading-context-title">{headline}</p>
        <span className="zen-reading-context-pct">
          {t('reading.focus_progress').replace('{percent}', String(progress))}
        </span>
        <button type="button" className="zen-reading-context-exit" onClick={exitFocus}>
          <X size={14} aria-hidden="true" />
          {t('reading.standard')}
        </button>
      </div>
    </div>
  );
}
