import React, { useEffect, useState } from 'react';
import { useStore } from '@nanostores/react';
import { $homepageMode, updateHomepageMode } from '../../lib/store';
import { useTranslations } from '../../i18n/utils';

const ANALIZA_HINT_KEY = 'analiza-mode-hint-dismissed';

export default function HomepageModeToggle({ lang = 'sr' }: { lang?: string }) {
  const mode = useStore($homepageMode);
  const [mounted, setMounted] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const t = useTranslations(lang as 'sr' | 'mk');

  useEffect(() => {
    setMounted(true);
    document.documentElement.dataset.homepageMode = mode;
  }, [mode]);

  useEffect(() => {
    if (!mounted || typeof localStorage === 'undefined') return;
    if (mode === 'analiza' && localStorage.getItem(ANALIZA_HINT_KEY) !== '1') {
      setShowHint(true);
    }
  }, [mode, mounted]);

  if (!mounted) return null;

  const setMode = (next: 'vesti' | 'analiza') => {
    updateHomepageMode(next);
    document.documentElement.dataset.homepageMode = next;
    if (next === 'analiza' && localStorage.getItem(ANALIZA_HINT_KEY) !== '1') {
      setShowHint(true);
    }
    if (next === 'vesti') {
      setShowHint(false);
    }
  };

  const dismissHint = () => {
    localStorage.setItem(ANALIZA_HINT_KEY, '1');
    setShowHint(false);
  };

  return (
    <div className="homepage-mode-wrap">
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
      {showHint && mode === 'analiza' && (
        <div className="homepage-mode-hint" role="note">
          <p>{t('home.mode_analiza_hint')}</p>
          <button type="button" className="homepage-mode-hint-dismiss" onClick={dismissHint}>
            {t('nav.close')}
          </button>
        </div>
      )}
    </div>
  );
}
