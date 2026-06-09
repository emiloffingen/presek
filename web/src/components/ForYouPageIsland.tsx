import { localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpRight,
  BellRing,
  BrainCircuit,
  Compass,
  Gauge,
  Layers,
  ListChecks,
  Loader2,
  Radio,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile } from '../lib/store.ts';
import PreferenceToggle from './PreferenceToggle.tsx';
import { NewsCard } from './NewsCard.tsx';
import OnboardingIsland from './OnboardingIsland.tsx';
import {
  buildCsrfHeadersAsync,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  buildSurfaceFollowSuggestions,
} from '../lib/personalization.js';
import { apiBaseUrl } from '../lib/apiBase';
import type { NewsCluster } from '../types';

interface ForYouPageIslandProps {
  initialClusters: NewsCluster[];
  initialError?: string | null;
  lang?: string;
}

type PersonalizedCluster = NewsCluster & { reason?: string };

function clusterTitle(cluster: PersonalizedCluster) {
  return cluster.synthetic_headline || cluster.articles?.[0]?.title || '';
}

function clusterTime(cluster: PersonalizedCluster) {
  return cluster.articles?.[0]?.ingested_at || cluster.articles?.[0]?.created_at || cluster.created_at || '';
}

function formatTime(value: string, lang: string) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(lang === 'mk' ? 'mk-MK' : 'sr-RS', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Europe/Skopje',
    }).format(new Date(value.replace('Z', '')));
  } catch {
    return '';
  }
}

export default function ForYouPageIsland({ initialClusters, initialError = null, lang = 'sr' }: ForYouPageIslandProps) {
  const profile = useStore($profile);
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [semanticError, setSemanticError] = useState<string | null>(null);
  const isMK = lang === 'mk';
  const hasSignals = hasPersonalizationSignal(profile);

  useEffect(() => {
    let cancelled = false;

    const fetchSemantic = async () => {
      if (!hasPersonalizationSignal(profile)) {
        if (!cancelled) {
          setSemanticResults([]);
          setSemanticError(null);
          setLoading(false);
        }
        return;
      }

      if (!cancelled) {
        setLoading(true);
        setSemanticError(null);
      }

      try {
        const res = await fetch(`${apiBaseUrl()}/profile/sync/personalized-news`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(await buildCsrfHeadersAsync()) },
          body: JSON.stringify({
            profile,
            limit: 36,
            lang: lang,
          }),
        });

        if (!res.ok) {
          throw new Error(`Semantic request failed: ${res.status}`);
        }

        const data = await res.json();
        if (!cancelled) {
          setSemanticResults(data.results || []);
        }
      } catch (e) {
        console.error('Semantic fetch failed', e);
        if (!cancelled) {
          setSemanticResults([]);
          setSemanticError(isMK ? 'Не можеме да ги вчитаме персонализираните препораки во овој момент.' : 'Ne možemo da pročitamo personalizovane preporuke u ovom trenutku.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchSemantic();
    return () => {
      cancelled = true;
    };
  }, [profile]);

  const mergedClusters = useMemo<PersonalizedCluster[]>(() => {
    const local = buildPersonalizedClusters(initialClusters, profile, 48, [], lang);
    const seen = new Set(semanticResults.map((r) => r.cluster_id));

    const combined = [
      ...semanticResults,
      ...local.filter((item) => item && item.cluster && !seen.has(item.cluster.cluster_id)).map((item) => ({
        ...item!.cluster,
        reason: item!.reason,
        has_synthesis: item!.cluster.has_synthesis,
        has_balanced: item!.cluster.has_balanced,
      })),
    ] as PersonalizedCluster[];

    if (combined.length === 0 && hasPersonalizationSignal(profile)) {
      return initialClusters.slice(0, 10).map((cluster) => ({
        ...cluster,
        reason: isMK ? 'Актуелно денес' : 'Aktuelno danas',
      }));
    }

    return combined;
  }, [initialClusters, semanticResults, profile, isMK, lang]);

  const followSuggestions = useMemo(() => {
    const suggestions = buildSurfaceFollowSuggestions(profile, 'for_you', { topicLimit: 5, sourceLimit: 3, lang });
    return [
      ...suggestions.topics.map((topic: any) => ({ ...topic, kind: 'topic' })),
      ...suggestions.sources.map((source: any) => ({ ...source, kind: 'source' })),
    ];
  }, [profile, lang]);

  const followedTopics = profile.followedTopics || [];
  const followedSources = profile.followedSources || [];
  const recentCount = profile.recentClusters?.length || 0;
  const signalStrength = Math.min(100, Math.round(followedTopics.length * 12 + followedSources.length * 16 + recentCount * 2));
  const priorityClusters = mergedClusters.slice(0, 3);
  const feedClusters = mergedClusters.slice(3, 15);
  const queueClusters = mergedClusters.slice(15, 21);
  const sourceCount = new Set(mergedClusters.flatMap((cluster) => cluster.articles?.map((article) => article.source) || [])).size;
  const synthesisCount = mergedClusters.filter((cluster) => cluster.has_synthesis).length;
  const pageError = semanticError || initialError;

  const categoryLeaders = useMemo(() => {
    const counts = new Map<string, number>();
    mergedClusters.forEach((cluster) => {
      const category = cluster.articles?.[0]?.category || cluster.articles?.[0]?.topic;
      if (!category) return;
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((left, right) => right[1] - left[1])
      .slice(0, 4);
  }, [mergedClusters]);

  if (loading) {
    return (
      <div className="for-you-loading">
        <Loader2 className="animate-spin" size={30} />
        <p>{isMK ? 'Го подготвуваме вашиот пресек...' : 'Pripremamo vaš Presek...'}</p>
      </div>
    );
  }

  if (!hasSignals) {
    return (
      <div className="for-you-dashboard">
        <section className="for-you-cold-start">
          <div className="cold-start-copy">
            <span className="for-you-kicker-line"><Compass size={16} /> {isMK ? 'Почеток' : 'Početak'}</span>
            <h1>{isMK ? 'Направете свој Пресек' : 'Napravite svoj Presek'}</h1>
            <p>
              {isMK
                ? 'Изберете неколку теми или извори. Страницата потоа ќе ги подреди вестите според вашите сигнали, без регистрација.'
                : 'Izaberite nekoliko tema ili izvora. Stranica zatim slaže vesti prema vašim signalima, bez registracije.'}
            </p>
          </div>
          <div className="cold-start-panel">
            <OnboardingIsland lang={lang} />
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="for-you-dashboard">
      <section className="for-you-hero">
        <div className="for-you-hero-copy">
          <span className="for-you-kicker-line">
            <Sparkles size={16} /> {isMK ? 'За Вас' : 'Za Vas'}
          </span>
          <h1>{isMK ? 'Личен дневен пресек' : 'Lični dnevni presek'}</h1>
          <p>
            {isMK
              ? 'Приоритети, нови агли и следни теми од вестите што најдобро се совпаѓаат со вашето читање.'
              : 'Prioriteti, novi uglovi i sledeće teme iz vesti koje se najbolje poklapaju sa vašim čitanjem.'}
          </p>
        </div>

        <div className="for-you-signal-panel" aria-label={isMK ? 'Состојба на профилот' : 'Stanje profila'}>
          <div className="signal-head">
            <Gauge size={18} />
            <span>{isMK ? 'Сигнал на профилот' : 'Signal profila'}</span>
            <strong>{signalStrength}%</strong>
          </div>
          <div className="signal-meter" aria-hidden="true">
            <span style={{ width: `${signalStrength}%` }}></span>
          </div>
          <div className="signal-metrics">
            <span title={isMK ? 'Следени сигнали (теми и извори)' : 'Praćeni signali (teme i izvori)'}>
              <BellRing size={13} /> {followedTopics.length + followedSources.length}
              <small className="ml-1 text-[9px] opacity-70 font-normal">{isMK ? 'сигнали' : 'signala'}</small>
            </span>
            <span title={isMK ? 'Препорачани приказни' : 'Preporučene priče'}>
              <Layers size={13} /> {mergedClusters.length}
              <small className="ml-1 text-[9px] opacity-70 font-normal">{isMK ? 'вести' : 'vesti'}</small>
            </span>
            <span title={isMK ? 'Опфатени извори' : 'Obuhvaćeni izvori'}>
              <Radio size={13} /> {sourceCount}
              <small className="ml-1 text-[9px] opacity-70 font-normal">{isMK ? 'извори' : 'izvora'}</small>
            </span>
          </div>
        </div>
      </section>

      {pageError && (
        <div className="for-you-alert">
          <BrainCircuit size={16} />
          <span>{pageError}</span>
        </div>
      )}

      <div className="for-you-layout">
        <main className="for-you-main">
          <section className="for-you-section-head">
            <div>
              <span>{isMK ? 'Приоритет' : 'Prioritet'}</span>
              <h2>{isMK ? 'Најрелевантно сега' : 'Najrelevantnije sada'}</h2>
            </div>
            <a href={localePathForLang('/settings', isMK ? 'mk' : 'sr')} className="for-you-text-link">
              <SlidersHorizontal size={14} /> {isMK ? 'Прилагоди' : 'Podesi'}
            </a>
          </section>

          {priorityClusters.length > 0 ? (
            <div className="priority-lane">
              {priorityClusters.map((cluster, index) => (
                <article key={cluster.cluster_id} className={`priority-story ${index === 0 ? 'is-primary' : ''}`}>
                  <div className="story-reason">
                    <BrainCircuit size={12} />
                    <span>{cluster.reason || (isMK ? 'Совпаѓање со профилот' : 'Poklapanje sa profilom')}</span>
                  </div>
                  <NewsCard
                    cluster={cluster}
                    variant={index === 0 ? 'featured' : 'standard'}
                    isLead={index === 0}
                    lang={lang}
                  />
                </article>
              ))}
            </div>
          ) : (
            <div className="for-you-empty">
              <p>{isMK ? 'Немаме нови вести за вашите специфични интереси во овој момент.' : 'Nemamo novih vesti za vaše specifične interese u ovom trenutku.'}</p>
            </div>
          )}

          {feedClusters.length > 0 && (
            <>
              <section className="for-you-section-head is-secondary">
                <div>
                  <span>{isMK ? 'Продолжете' : 'Nastavite'}</span>
                  <h2>{isMK ? 'Уште препораки' : 'Još preporuka'}</h2>
                </div>
              </section>
              <div className="recommendation-grid">
                {feedClusters.map((cluster) => (
                  <article key={cluster.cluster_id} className="recommendation-tile">
                    <div className="story-reason">
                      <TrendingUp size={12} />
                      <span>{cluster.reason || (isMK ? 'Блиску до вашите интереси' : 'Blizu vaših interesovanja')}</span>
                    </div>
                    <NewsCard cluster={cluster} variant="compact" lang={lang} />
                  </article>
                ))}
              </div>
            </>
          )}
        </main>

        <aside className="for-you-rail">
          <section className="rail-panel">
            <h3><ListChecks size={16} /> {isMK ? 'Ваш профил' : 'Vaš profil'}</h3>
            <div className="profile-stat-grid">
              <span><strong>{followedTopics.length}</strong>{isMK ? 'теми' : 'tema'}</span>
              <span><strong>{followedSources.length}</strong>{isMK ? 'извори' : 'izvora'}</span>
              <span><strong>{synthesisCount}</strong>{isMK ? 'синтези' : 'sinteza'}</span>
            </div>
            <div className="followed-stack">
              {followedTopics.slice(0, 8).map((topic: string) => (
                <PreferenceToggle key={`topic:${topic}`} kind="topic" value={topic} lang={lang} analyticsSurface="for_you_page" />
              ))}
              {followedSources.slice(0, 6).map((source: string) => (
                <PreferenceToggle key={`source:${source}`} kind="source" value={source} lang={lang} analyticsSurface="for_you_page" />
              ))}
            </div>
          </section>

          {categoryLeaders.length > 0 && (
            <section className="rail-panel">
              <h3><Layers size={16} /> {isMK ? 'Фокус денес' : 'Fokus danas'}</h3>
              <div className="category-bars">
                {categoryLeaders.map(([category, count]) => (
                  <div key={category} className="category-row">
                    <span>{category}</span>
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            </section>
          )}

          {followSuggestions.length > 0 && (
            <section className="rail-panel">
              <h3><Compass size={16} /> {isMK ? 'Додај сигнал' : 'Dodaj signal'}</h3>
              <div className="discover-stack">
                {followSuggestions.map((item: any) => (
                  <div key={`${item.kind}:${item.value}`} className="discover-suggestion">
                    <div>
                      <strong>{item.value}</strong>
                      <span>{item.kind === 'topic' ? (isMK ? 'тема' : 'tema') : (isMK ? 'извор' : 'izvor')}</span>
                    </div>
                    <PreferenceToggle
                      kind={item.kind as any}
                      value={item.value}
                      lang={lang}
                      analyticsSurface="for_you_page_discover"
                    />
                  </div>
                ))}
              </div>
            </section>
          )}

          {queueClusters.length > 0 && (
            <section className="rail-panel">
              <h3><Radio size={16} /> {isMK ? 'Следно' : 'Sledeće'}</h3>
              <div className="next-stack">
                {queueClusters.map((cluster) => (
                  <a key={cluster.cluster_id} href={localePathForLang(`/cluster/${cluster.cluster_id}`, isMK ? 'mk' : 'sr')} className="next-item">
                    <span>{formatTime(clusterTime(cluster), lang)}</span>
                    <strong>{clusterTitle(cluster)}</strong>
                    <ArrowUpRight size={13} />
                  </a>
                ))}
              </div>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
