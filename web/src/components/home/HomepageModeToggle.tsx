import React, { useEffect, useState } from 'react';
import { useStore } from '@nanostores/react';
import { $homepageMode, updateHomepageMode } from '../../lib/store';
import { useTranslations } from '../../i18n/utils';

const ANALIZA_HINT_KEY = 'analiza-mode-hint-dismissed';
const VESTI_HINT_KEY = 'vesti-mode-hint-dismissed';

export default function HomepageModeToggle({ lang = 'sr' }: { lang?: string }) {
  const mode = useStore($homepageMode);
  const [mounted, setMounted] = useState(false);
  const [showAnalizaHint, setShowAnalizaHint] = useState(false);
  const [showVestiHint, setShowVestiHint] = useState(false);
  const t = useTranslations(lang as 'sr' | 'mk');

  useEffect(() => {
    setMounted(true);
    document.documentElement.dataset.homepageMode = mode;
  }, [mode]);

  useEffect(() => {
    if (!mounted || typeof localStorage === 'undefined') return;
    if (mode === 'analiza' && localStorage.getItem(ANALIZA_HINT_KEY) !== '1') {
      setShowAnalizaHint(true);
      setShowVestiHint(false);
      return;
    }
    if (mode === 'vesti' && localStorage.getItem(VESTI_HINT_KEY) !== '1') {
      setShowVestiHint(true);
      setShowAnalizaHint(false);
    }
  }, [mode, mounted]);

  if (!mounted) return null;

  const setMode = (next: 'vesti' | 'analiza') => {
    updateHomepageMode(next);
    document.documentElement.dataset.homepageMode = next;
    if (next === 'analiza' && localStorage.getItem(ANALIZA_HINT_KEY) !== '1') {
      setShowAnalizaHint(true);
      setShowVestiHint(false);
    }
    if (next === 'vesti') {
      setShowAnalizaHint(false);
      if (localStorage.getItem(VESTI_HINT_KEY) !== '1') {
        setShowVestiHint(true);
      }
    }
  };

  const dismissAnalizaHint = () => {
    localStorage.setItem(ANALIZA_HINT_KEY, '1');
    setShowAnalizaHint(false);
  };

  const dismissVestiHint = () => {
    localStorage.setItem(VESTI_HINT_KEY, '1');
    setShowVestiHint(false);
  };

  return (
    <div className="homepage-mode-wrap homepage-mode-wrap--prominent">
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
      {showAnalizaHint && mode === 'analiza' && (
        <div className="homepage-mode-hint" role="note">
          <p>{t('home.mode_analiza_hint')}</p>
          <button type="button" className="homepage-mode-hint-dismiss" onClick={dismissAnalizaHint}>
            {t('nav.close')}
          </button>
        </div>
      )}
      {showVestiHint && mode === 'vesti' && (
        <div className="homepage-mode-hint homepage-mode-hint--vesti" role="note">
          <p>{t('home.mode_vesti_hint')}</p>
          <button type="button" className="homepage-mode-hint-dismiss" onClick={dismissVestiHint}>
            {t('nav.close')}
          </button>
        </div>
      )}
      {mode === 'vesti' && !showVestiHint && (
        <button type="button" className="homepage-mode-cta" onClick={() => setMode('analiza')}>
          {t('home.mode_open_analiza')}
        </button>
      )}
    </div>
  );
}
