import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { applyReadingMode, saveReadingMode } from '../../lib/readingMode';
import { useClientTranslations } from '../../i18n/clientTranslations';
import { settings } from '../../i18n/namespaces/settings';

export default function ZenReadingContext({
  headline,
  lang = 'sr',
}: {
  headline: string;
  lang?: string;
}) {
  const t = useClientTranslations(lang as 'sr' | 'mk', settings);
  const [visible, setVisible] = useState(false);

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

  if (!visible) return null;

  const exitFocus = () => {
    saveReadingMode('standard');
    applyReadingMode('standard');
  };

  return (
    <div className="zen-reading-context" role="status">
      <p className="zen-reading-context-title">{headline}</p>
      <button type="button" className="zen-reading-context-exit" onClick={exitFocus}>
        <X size={14} aria-hidden="true" />
        {t('reading.standard')}
      </button>
    </div>
  );
}
