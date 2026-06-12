import React, { useState } from 'react';
import { useTranslations } from '../../i18n/utils';

export default function ClusterSidebarToggle({ lang = 'sr' }: { lang?: string }) {
  const t = useTranslations(lang as 'sr' | 'mk');
  const [expanded, setExpanded] = useState(false);

  const toggle = () => {
    const aside = document.querySelector('.editorial-sidebar-col');
    if (!aside) return;
    const next = !expanded;
    setExpanded(next);
    aside.classList.toggle('is-expanded', next);
  };

  return (
    <button type="button" className="cluster-sidebar-toggle" onClick={toggle}>
      {t('cluster.show_sidebar')}
    </button>
  );
}
