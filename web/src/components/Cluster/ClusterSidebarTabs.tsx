import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from '../../i18n/utils';
import { SourceSpectrum } from '../SourceSpectrum';
import SourceComparisonIsland from '../SourceComparisonIsland';
import { MediaPulseRadar } from '../MediaPulseRadar';
import NewsletterIsland from '../NewsletterIsland';
import ClusterFollowSuggestionsIsland from '../ClusterFollowSuggestionsIsland';
import EntityContextCard from '../EntityContextCard';

type TabId = 'spectrum' | 'compare' | 'pulse' | 'more';

interface Props {
  lang?: string;
  articles: { source: string }[];
  allSourcesNames: string[];
  sentimentData: any;
  showCompare: boolean;
  showPulse: boolean;
  topic: string;
  source: string;
  adjacentTopic: string;
  keyEntities: string[];
}

export default function ClusterSidebarTabs({
  lang = 'sr',
  articles,
  allSourcesNames,
  sentimentData,
  showCompare,
  showPulse,
  topic,
  source,
  adjacentTopic,
  keyEntities,
}: Props) {
  const locale = lang === 'mk' ? 'mk' : 'sr';
  const t = useTranslations(locale);
  const tabs = useMemo(() => {
    const items: { id: TabId; label: string; disabled?: boolean }[] = [
      { id: 'spectrum', label: t('cluster.tab_spectrum') },
      { id: 'compare', label: t('cluster.tab_compare'), disabled: !showCompare },
      { id: 'pulse', label: t('cluster.tab_pulse'), disabled: !showPulse },
      { id: 'more', label: t('cluster.tab_more') },
    ];
    return items.filter((tab) => !tab.disabled);
  }, [showCompare, showPulse, t]);

  const [activeTab, setActiveTab] = useState<TabId>('spectrum');
  const [visited, setVisited] = useState<Set<TabId>>(() => new Set(['spectrum']));

  const selectTab = useCallback((tab: TabId) => {
    setActiveTab(tab);
    setVisited((prev) => new Set(prev).add(tab));
  }, []);

  useEffect(() => {
    const onReadingMode = (event: Event) => {
      const mode = (event as CustomEvent<{ mode?: string }>).detail?.mode;
      if (mode === 'compare' && showCompare) {
        selectTab('compare');
      }
    };
    const onSidebarTab = (event: Event) => {
      const tab = (event as CustomEvent<{ tab?: TabId }>).detail?.tab;
      if (tab) {
        selectTab(tab);
      }
    };

    window.addEventListener('presek:reading-mode-changed', onReadingMode);
    window.addEventListener('presek:sidebar-tab', onSidebarTab);
    if (document.body.classList.contains('compare-mode') && showCompare) {
      selectTab('compare');
    }

    return () => {
      window.removeEventListener('presek:reading-mode-changed', onReadingMode);
      window.removeEventListener('presek:sidebar-tab', onSidebarTab);
    };
  }, [showCompare, selectTab]);

  return (
    <div className="cluster-sidebar-tabs" data-active-tab={activeTab}>
      <div className="cluster-sidebar-tablist" role="tablist" aria-label={t('cluster.sidebar_tools')}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`cluster-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`cluster-panel-${tab.id}`}
            className={`cluster-sidebar-tab ${activeTab === tab.id ? 'is-active' : ''}`}
            onClick={() => selectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="cluster-sidebar-panels">
        {visited.has('spectrum') && (
          <section
            id="cluster-panel-spectrum"
            role="tabpanel"
            aria-labelledby="cluster-tab-spectrum"
            hidden={activeTab !== 'spectrum'}
            className="cluster-sidebar-panel source-spectrum-panel"
          >
            <SourceSpectrum articles={articles as any} lang={locale} />
          </section>
        )}

        {showCompare && visited.has('compare') && (
          <section
            id="cluster-panel-compare"
            role="tabpanel"
            aria-labelledby="cluster-tab-compare"
            hidden={activeTab !== 'compare'}
            className="cluster-sidebar-panel compare-source-diff-panel source-comparison-panel"
          >
            <SourceComparisonIsland allSources={allSourcesNames} lang={locale} />
          </section>
        )}

        {showPulse && visited.has('pulse') && (
          <section
            id="cluster-panel-pulse"
            role="tabpanel"
            aria-labelledby="cluster-tab-pulse"
            hidden={activeTab !== 'pulse'}
            className="cluster-sidebar-panel"
          >
            <MediaPulseRadar data={sentimentData} lang={locale} />
          </section>
        )}

        {visited.has('more') && (
          <section
            id="cluster-panel-more"
            role="tabpanel"
            aria-labelledby="cluster-tab-more"
            hidden={activeTab !== 'more'}
            className="cluster-sidebar-panel cluster-sidebar-more"
          >
            <NewsletterIsland lang={locale} />
            <ClusterFollowSuggestionsIsland
              topic={topic}
              source={source}
              adjacentTopic={adjacentTopic}
              lang={locale}
            />
            {keyEntities.length > 0 && (
              <div className="cluster-sidebar-entities">
                <h4 className="sidebar-label">{t('cluster.key_entities')}</h4>
                <div className="cluster-sidebar-entities-list">
                  {keyEntities.map((name) => (
                    <EntityContextCard key={name} name={name} lang={locale} />
                  ))}
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
