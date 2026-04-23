import React, { useEffect, useMemo, useState } from 'react';
import { Compass, Sparkles, BrainCircuit, Loader2 } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import { NewsCard } from './NewsCard.tsx';
import OnboardingIsland from './OnboardingIsland.tsx';
import {
  buildPersonalizedClusters,
  loadReaderProfile,
  subscribeToReaderProfile,
  hasPersonalizationSignal,
  buildSurfaceFollowSuggestions,
} from '../lib/personalization.js';
import { apiBaseUrl } from '../lib/apiBase';
import type { NewsCluster } from '../types';

interface ForYouPageIslandProps {
  initialClusters: NewsCluster[];
  initialError?: string | null;
}

interface ReaderProfile {
  recentClusters: any[];
  followedTopics: string[];
  followedSources: string[];
}

export default function ForYouPageIsland({ initialClusters, initialError = null }: ForYouPageIslandProps) {
  const [profile, setProfile] = useState<ReaderProfile>(loadReaderProfile());
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [semanticError, setSemanticError] = useState<string | null>(null);

  // 1. Load Local Profile & Subscribe
  useEffect(() => {
    const unsubscribe = subscribeToReaderProfile((nextProfile: ReaderProfile) => {
      setProfile(nextProfile);
    });
    return unsubscribe;
  }, []);

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
          setSemanticError('Не можеме да ги вчитаме персонализираните препораки во моментов.');
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

  // 3. Hybrid Merging
  const mergedClusters = useMemo(() => {
    const local = buildPersonalizedClusters(initialClusters, profile, 48);
    const seen = new Set(semanticResults.map(r => r.cluster_id));
    
    // Combine semantic results (server-side brain) with local keyword matches
    return [
      ...semanticResults,
      ...local.filter(item => item && item.cluster && !seen.has(item.cluster.cluster_id)).map(item => ({
        ...item!.cluster,
        reason: item!.reason,
        has_synthesis: item!.cluster.has_synthesis,
        has_balanced: item!.cluster.has_balanced
      }))
    ];
  }, [initialClusters, semanticResults, profile]);

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
      <div className="flex flex-col items-center justify-center py-20">
        <Loader2 className="animate-spin text-nyt-accent mb-4" size={32} />
        <p className="font-serif italic text-muted-foreground">Генерираме ваш личен преглед...</p>
      </div>
    );
  }

  if (!hasPersonalizationSignal(profile)) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <header className="mb-12 text-center">
            <div className="inline-flex items-center justify-center p-3 bg-nyt-accent/10 rounded-full mb-4">
                <Compass className="text-nyt-accent" size={24} />
            </div>
            <h1 className="font-serif text-4xl font-black mb-4">Добредојдовте во „За Вас“</h1>
            <p className="text-lg text-secondary-foreground max-w-xl mx-auto">
                Оваа страница е празна бидејќи сè уште не знаеме што ве интересира. Изберете неколку теми за да започнете.
            </p>
        </header>
        <OnboardingIsland />
      </div>
    );
  }

  return (
    <div className="for-you-page-grid grid grid-cols-1 lg:grid-cols-3 gap-12">
      <div className="lg:col-span-2 space-y-12">
        <header className="pb-8 border-b border-border">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="text-nyt-accent" size={18} />
            <span className="font-sans text-[11px] font-black uppercase tracking-[0.2em] text-nyt-accent">Интелигенција</span>
          </div>
          <h1 className="font-serif text-4xl md:text-5xl font-black italic">Личен <span className="serif-display">Пресек</span></h1>
          <p className="mt-4 font-nyt-body text-lg text-secondary-foreground leading-relaxed">
             Вашиот дневен преглед на вести, прецизно синтетизиран според темите, личностите и изворите што ги следите.
          </p>
        </header>

        {pageError && mergedClusters.length === 0 && (
          <div className="py-12 text-center border border-dashed border-border rounded-xl bg-secondary/5">
            <p className="font-serif text-2xl font-bold mb-3">Не можеме да го вчитаме „За Вас“</p>
            <p className="text-muted-foreground">{pageError}</p>
          </div>
        )}

        {mergedClusters.length > 0 ? (
          <div className="space-y-10">
            {mergedClusters.map((cluster, idx) => (
              <div key={cluster.cluster_id} className="relative group">
                {cluster.reason && (
                    <div className="absolute -left-4 top-0 bottom-0 w-1 bg-nyt-accent/20 group-hover:bg-nyt-accent transition-colors hidden md:block"></div>
                )}
                <div className="mb-2 flex items-center gap-2">
                    <BrainCircuit size={12} className="text-nyt-accent/60" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                        {cluster.reason || 'Препорачано'}
                    </span>
                </div>
                <NewsCard 
                  cluster={cluster} 
                  variant={idx === 0 ? 'featured' : 'standard'}
                  isLead={idx === 0}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="py-20 text-center border border-dashed border-border rounded-xl">
             <p className="font-serif italic text-muted-foreground">
               {pageError || 'Немаме нови вести за вашите специфични интереси во овој момент. Пробајте да додадете повеќе теми.'}
             </p>
          </div>
        )}
      </div>

      <aside className="space-y-10">
        {/* Following Section */}
        <section className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <h3 className="font-sans text-[11px] font-black uppercase tracking-widest text-foreground mb-6 pb-2 border-b border-border">Ваши Интереси</h3>
          
          <div className="space-y-8">
            {profile.followedTopics.length > 0 && (
                <div>
                    <p className="text-[10px] font-black uppercase text-muted-foreground mb-3">Теми</p>
                    <div className="flex flex-wrap gap-2">
                        {profile.followedTopics.map((t: string) => (
                            <PreferenceToggle key={t} kind="topic" value={t} analyticsSurface="for_you_page" />
                        ))}
                    </div>
                </div>
            )}

            {profile.followedSources.length > 0 && (
                <div>
                    <p className="text-[10px] font-black uppercase text-muted-foreground mb-3">Извори</p>
                    <div className="flex flex-wrap gap-2">
                        {profile.followedSources.map((s: string) => (
                            <PreferenceToggle key={s} kind="source" value={s} analyticsSurface="for_you_page" />
                        ))}
                    </div>
                </div>
            )}
            
            <a href="/settings" className="block text-center py-2 text-[10px] font-black uppercase tracking-widest text-nyt-accent hover:underline">
                Уреди ги сите интереси →
            </a>
          </div>
        </section>

        {/* Discovery Suggestions */}
        {followSuggestions.length > 0 && (
            <section className="bg-nyt-accent/5 border border-nyt-accent/20 rounded-2xl p-6">
                <h3 className="font-sans text-[11px] font-black uppercase tracking-widest text-nyt-accent mb-6">Откријте повеќе</h3>
                <div className="space-y-3">
                    {followSuggestions.map(item => (
                        <div key={item.value} className="flex items-center justify-between gap-4 p-2 bg-card border border-border rounded-lg group">
                            <div className="min-w-0">
                                <p className="text-xs font-bold truncate">{item.value}</p>
                                <p className="text-[9px] text-muted-foreground uppercase">{item.kind === 'topic' ? 'Тема' : 'Извор'}</p>
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
