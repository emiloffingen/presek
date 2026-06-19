import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { applyReadingMode, loadReadingMode, saveReadingMode } from '../../lib/readingMode';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { settings } from '../../i18n/namespaces/settings';

const SESSION_KEY = 'cluster-mobile-focus-dismissed';

export default function ClusterMobileFocusIsland({ lang = 'sr' }: { lang?: string }) {
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!window.matchMedia('(max-width: 768px)').matches) return;
    if (sessionStorage.getItem(SESSION_KEY) === '1') return;
    if (localStorage.getItem('reading-mode')) return;
    if (loadReadingMode() !== 'standard') return;

    applyReadingMode('focus');
    setVisible(true);
  }, []);

  const dismiss = () => {
    sessionStorage.setItem(SESSION_KEY, '1');
    saveReadingMode('standard');
    applyReadingMode('standard');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="cluster-mobile-focus-banner" role="status">
      <p>{t('reading.mobile_focus_banner')}</p>
      <button type="button" className="cluster-mobile-focus-exit" onClick={dismiss}>
        <X size={14} aria-hidden="true" />
        {t('reading.mobile_focus_exit')}
      </button>
    </div>
  );
}
