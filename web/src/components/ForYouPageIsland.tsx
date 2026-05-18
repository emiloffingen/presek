import React, { useEffect, useMemo, useState } from 'react';
import { Compass, Sparkles, BrainCircuit, Loader2 } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, updateProfile } from '../lib/store.ts';
import { ErrorBoundary } from './ui/ErrorBoundary.tsx';
import PreferenceToggle from './PreferenceToggle.tsx';
import { NewsCard } from './NewsCard.tsx';
import OnboardingIsland from './OnboardingIsland.tsx';
import {
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

export default function ForYouPageIsland({ initialClusters, initialError = null, lang = 'sr' }: ForYouPageIslandProps) {
  const profile = useStore($profile);
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [semanticError, setSemanticError] = useState<string | null>(null);
  const isMK = lang === 'mk';

  // 2. Fetch semantic recommendations whenever personalization signals change.
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile,
            limit: 36,
            lang: lang
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
  }, [profile, lang, isMK]);

  // 3. Hybrid Merging
  const mergedClusters = useMemo(() => {
    const local = buildPersonalizedClusters(initialClusters, profile, 48);
    const seen = new Set(semanticResults.map(r => r.cluster_id));

    // Combine semantic results (server-side brain) with local keyword matches
    const combined = [
      ...semanticResults,
      ...local.filter(item => item && item.cluster && !seen.has(item.cluster.cluster_id)).map(item => ({
        ...item!.cluster,
        reason: item!.reason,
        has_synthesis: item!.cluster.has_synthesis,
        has_balanced: item!.cluster.has_balanced
      }))
    ];

    // COLD START FALLBACK: If we have followed topics but NO matches,
    // provide the top 10 most relevant from the initial set anyway
    if (combined.length === 0 && hasPersonalizationSignal(profile)) {
        return initialClusters.slice(0, 10).map(c => ({
            ...c,
            reason: isMK ? 'Актуелно денес' : 'Aktuelno danas'
        }));
    }

    return combined;
  }, [initialClusters, semanticResults, profile, isMK]);

  const followSuggestions = useMemo(() => {
    const suggestions = buildSurfaceFollowSuggestions(profile, 'for_you', { topicLimit: 4, sourceLimit: 2 });
    return [
      ...suggestions.topics.map((t: any) => ({ ...t, kind: 'topic' })),
      ...suggestions.sources.map((s: any) => ({ ...s, kind: 'source' }))
    ];
  }, [profile]);

  const pageError = semanticError || initialError;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-40">
        <Loader2 className="animate-spin text-nyt-accent mb-4" size={32} />
        <p className="font-serif italic text-muted-foreground">{isMK ? 'Го генерираме вашиот персонализиран преглед...' : 'Generišemo vaš personalizovan pregled...'}</p>
      </div>
    );
  }

  if (!hasPersonalizationSignal(profile)) {
    return (
      <div className="max-w-4xl mx-auto py-20">
        <header className="mb-12 text-center">
            <div className="inline-flex items-center justify-center p-3 bg-nyt-accent/10 rounded-full mb-4">
                <Compass className="text-nyt-accent" size={24} />
            </div>
            <h1 className="font-serif text-4xl md:text-5xl font-black mb-4 tracking-tight">{isMK ? 'Вашиот личен простор' : 'Vaš lični prostor'}</h1>
            <p className="text-lg md:text-xl text-secondary-foreground max-w-xl mx-auto italic font-serif">
                {isMK
                  ? 'оваа страница е место каде што Пресек го прилагодува вашиот ритам. Изберете теми што ве интересираат за да започнете.'
                  : 'ova stranica je mesto gde Presek prilagođava vaš ritam. Izaberite teme koje vas interesuju da biste započeli.'}
            </p>
        </header>
        <div className="bg-secondary/5 border border-border p-8 md:p-12 rounded-3xl shadow-inner">
            <OnboardingIsland lang={lang} />
        </div>
      </div>
    );
  }

  return (
    <div className="for-you-page-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-[var(--grid-gap)] items-stretch mt-12">
      <div className="lg:col-span-2 space-y-12">
        <header className="pb-10 border-b border-border">
          <div className="flex items-center gap-[var(--grid-gap)] mb-3">
            <Sparkles className="text-nyt-accent" size={16} />
            <span className="font-sans text-[10px] font-black uppercase tracking-[0.25em] text-nyt-accent">{isMK ? 'УРЕДНИЧКА СИНТЕЗА' : 'UREDNIČKA SINTEZA'}</span>
          </div>
          <h1 className="font-serif text-[clamp(2rem,6vw,4rem)] font-black leading-[0.9] mb-6 italic">{isMK ? 'Личен' : 'Lični'} <span className="serif-display font-light not-italic">{isMK ? 'Пресек' : 'Presek'}</span></h1>
          <p className="mt-4 font-nyt-body text-[clamp(1rem,2vw,1.25rem)] text-secondary-foreground leading-relaxed italic max-w-2xl">
             {isMK
               ? 'Вашиот дневен преглед, синтетизиран според темите, личностите и изворите што ги следите.'
               : 'Vaš dnevni pregled, sintetisan prema temama, ličnostima i izvorima koje pratite.'}
          </p>
        </header>

        {pageError && mergedClusters.length === 0 && (
          <div className="py-12 text-center border border-dashed border-border rounded-xl bg-secondary/5">
            <p className="font-serif text-2xl font-bold mb-3">{isMK ? 'Не можеме да вчитаме „За Вас“' : 'Ne možemo da učitamo „Za Vas“'}</p>
            <p className="text-muted-foreground">{pageError}</p>
          </div>
        )}

        {mergedClusters.length > 0 ? (
          <div className="space-y-16">
            {mergedClusters.map((cluster, idx) => (
              <div key={cluster.cluster_id} className="relative group">
                <div className="mb-4 flex items-center gap-[var(--grid-gap)]">
                    <div className="w-8 h-[1px] bg-nyt-accent/30"></div>
                    <BrainCircuit size={13} className="text-nyt-accent" />
                    <span className="text-[10px] font-black uppercase tracking-[0.15em] text-muted-foreground group-hover:text-nyt-accent transition-colors">
                        {cluster.reason || (isMK ? 'За Вас' : 'Za Vas')}
                    </span>
                </div>
                <NewsCard
                  cluster={cluster}
                  variant={idx === 0 ? 'featured' : 'standard'}
                  isLead={idx === 0}
                  lang={lang}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="py-20 text-center border border-dashed border-border rounded-xl">
             <p className="font-serif italic text-muted-foreground text-xl">
               {pageError || (isMK ? 'Немаме нови вести за вашите специфични интереси во овој момент.' : 'Nemamo novih vesti za vaše specifične interese u ovom trenutku.')}
             </p>
          </div>
        )}
      </div>

      <aside className="space-y-12">
        {/* Following Section */}
        <section className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-6 lg:p-8 shadow-sm">
          <h3 className="font-sans text-[10px] font-black uppercase tracking-widest text-foreground mb-8 pb-3 border-b border-zinc-100 dark:border-zinc-800">{isMK ? 'Ваши интереси' : 'Vaši interesi'}</h3>

          <div className="space-y-10">
            {profile.followedTopics.length > 0 && (
                <div>
                    <p className="text-[9px] font-black uppercase text-muted-foreground mb-4 tracking-widest">{isMK ? 'Теми' : 'Teme'}</p>
                    <div className="flex flex-wrap gap-[var(--grid-gap)]">
                        {profile.followedTopics.map((t: string) => (
                            <PreferenceToggle key={t} kind="topic" value={t} analyticsSurface="for_you_page" />
                        ))}
                    </div>
                </div>
            )}

            {profile.followedSources.length > 0 && (
                <div>
                    <p className="text-[9px] font-black uppercase text-muted-foreground mb-4 tracking-widest">{isMK ? 'извори' : 'izvori'}</p>
                    <div className="flex flex-wrap gap-[var(--grid-gap)]">
                        {profile.followedSources.map((s: string) => (
                            <PreferenceToggle key={s} kind="source" value={s} analyticsSurface="for_you_page" />
                        ))}
                    </div>
                </div>
            )}

            <a href={isMK ? "/mk/settings" : "/settings"} className="block text-center py-3 bg-secondary/50 rounded-lg text-[10px] font-black uppercase tracking-widest text-nyt-accent hover:bg-nyt-accent hover:text-white transition-all">
                {isMK ? 'Уредете ги вашите интереси →' : 'Uredite sva svoja interesovanja →'}
            </a>
          </div>
        </section>

        {/* Discovery Suggestions */}
        {followSuggestions.length > 0 && (
            <section className="bg-secondary/10 border border-border rounded-lg p-6 lg:p-8">
                <h3 className="font-sans text-[10px] font-black uppercase tracking-widest text-nyt-accent mb-8">{isMK ? 'Откријте повеќе' : 'Otkrijte više'}</h3>
                <div className="space-y-4">
                    {followSuggestions.map(item => (
                        <div key={item.value} className="flex items-center justify-between gap-[var(--grid-gap)] p-3 bg-background border border-border rounded-lg group hover:border-nyt-accent/30 transition-all">
                            <div className="min-w-0 flex-1">
                                <p className="text-[10px] font-black uppercase tracking-tighter leading-tight whitespace-normal break-words line-clamp-3 overflow-hidden text-ellipsis h-auto min-h-[4.5rem]">{item.value}</p>
                                <p className="text-[8px] text-muted-foreground uppercase font-black mt-0.5">{item.kind === 'topic' ? (isMK ? 'Тема' : 'Tema') : (isMK ? 'извор' : 'izvor')}</p>
                            </div>
                            <PreferenceToggle
                                kind={item.kind as any}
                                value={item.value}
                                analyticsSurface="for_you_page_discover"
                            />
                        </div>
                    ))}
                </div>
            </section>
        )}
      </aside>
    </div>
  );
}
