import React, { useEffect, useState } from 'react';
import { useStore } from '@nanostores/react';
import { $homepageMode, updateHomepageMode } from '../../lib/store';
import { useTranslations } from '../../i18n/utils';

export default function HomepageModeToggle({ lang = 'sr' }: { lang?: string }) {
  const mode = useStore($homepageMode);
  const [mounted, setMounted] = useState(false);
  const t = useTranslations(lang as 'sr' | 'mk');

  useEffect(() => {
    setMounted(true);
    document.documentElement.dataset.homepageMode = mode;
  }, [mode]);

  if (!mounted) return null;

  const setMode = (next: 'vesti' | 'analiza') => {
    updateHomepageMode(next);
    document.documentElement.dataset.homepageMode = next;
  };

  return (
    <div className="homepage-mode-toggle" role="group" aria-label={t('home.mode_label')}>
      <button
        type="button"
        className={`homepage-mode-btn ${mode === 'vesti' ? 'is-active' : ''}`}
        aria-pressed={mode === 'vesti'}
        onClick={() => setMode('vesti')}
      >
        {t('home.mode_vesti')}
      </button>
      <button
        type="button"
        className={`homepage-mode-btn ${mode === 'analiza' ? 'is-active' : ''}`}
        aria-pressed={mode === 'analiza'}
        onClick={() => setMode('analiza')}
      >
        {t('home.mode_analiza')}
      </button>
    </div>
  );
}
