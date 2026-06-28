import { localePathForLang } from '../lib/localePaths';
import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Clock3, Newspaper, Sparkles, X, Trash2, Check } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, updateProfile } from '../lib/store.ts';
import { useClientTranslations } from '../i18n/clientTranslations';
import { settings } from '../i18n/namespaces/settings';
import {
  buildSurfaceFollowSuggestions,
  recordSuggestionFollow,
  recordSuggestionImpressions,
  sendSuggestionEvents,
} from '../lib/personalization.js';

function summarizeRecent(profile: any) {
  const recent = Array.isArray(profile?.recentClusters) ? profile.recentClusters : [];
  return recent.slice(0, 5).map((item: any) => ({
    clusterId: String(item?.cluster_id || '').trim(),
    title: String(item?.title || '').trim(),
    topic: String(item?.topic || item?.category || '').trim(),
    source: String(item?.primarySource || '').trim(),
  })).filter((item: any) => item.clusterId && item.title);
}

export default function SettingsProfileIsland({ lang = 'sr' }: { lang?: 'sr' | 'mk' }) {
  const profile = useStore($profile);
  const [resetConfirm, setResetConfirm] = useState(false);
  const t = useClientTranslations(lang, settings);
  const locale = lang;

  useEffect(() => {
    let cancelled = false;
    const recent = Array.isArray(profile?.recentClusters) ? profile.recentClusters.slice(0, 5) : [];
    if (recent.length === 0) return;

    const validateRecent = async () => {
      try {
        const checks = await Promise.all(
          recent.map(async (item: any) => {
            const clusterId = String(item?.cluster_id || '').trim();
            if (!clusterId) return { clusterId, ok: false };
            const res = await fetch(`/api/cluster/${clusterId}`);
            return { clusterId, ok: res.ok };
          })
        );
        if (cancelled) return;

        const invalidIds = new Set(checks.filter((item) => !item.ok).map((item) => item.clusterId));
        if (invalidIds.size === 0) return;

        const nextRecent = (profile?.recentClusters || []).filter((item: any) => !invalidIds.has(String(item?.cluster_id || '').trim()));
        updateProfile({ recentClusters: nextRecent });
      } catch {
        // Ignore cleanup failures; they should not block the settings view.
      }
    };

    validateRecent();
    return () => {
      cancelled = true;
    };
  }, [profile.recentClusters]);

  const followedTopics = useMemo(() => profile?.followedTopics || [], [profile]);
  const followedSources = useMemo(() => profile?.followedSources || [], [profile]);
  const recentItems = useMemo(() => summarizeRecent(profile), [profile]);

  const topFocusTopic = useMemo(() => {
    if (recentItems.length === 0) return null;
    const counts: Record<string, number> = {};
    recentItems.forEach((item: any) => {
        const t = item.topic || 'vesti';
        counts[t] = (counts[t] || 0) + 1;
    });
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return entries.length > 0 ? entries[0][0] : null;
  }, [recentItems]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'settings', { topicLimit: 3, sourceLimit: 2, lang }),
    [profile, lang]
  );

  useEffect(() => {
    const result = recordSuggestionImpressions('settings', [
      ...recommendations.topics.map((item) => ({ kind: 'topic', value: item.value })),
      ...recommendations.sources.map((item) => ({ kind: 'source', value: item.value })),
    ]);
    sendSuggestionEvents(
      result.recorded.map((item) => ({
        surface: 'settings',
        eventType: 'impression',
        suggestionKind: item.kind,
        value: item.value,
      }))
    );
  }, [recommendations]);

  const removeFollow = (kind: 'topic' | 'source', value: string) => {
    const field = kind === 'source' ? 'followedSources' : 'followedTopics';
    const newList = (profile[field] || []).filter((v: string) => v !== value);
    updateProfile({ [field]: newList });
  };

  const addFollow = (kind: 'topic' | 'source', value: string) => {
    const field = kind === 'source' ? 'followedSources' : 'followedTopics';
    const currentList = profile[field] || [];
    const newList = [...new Set([...currentList, value])].slice(0, 12);

    updateProfile({ [field]: newList });

    const tracked = recordSuggestionFollow('settings', kind, value);
    if (tracked.recorded) {
        sendSuggestionEvents([{ surface: 'settings', eventType: 'follow', suggestionKind: kind, value }]);
    }
  };

  const handleResetProfile = () => {
    if (!resetConfirm) {
      setResetConfirm(true);
      setTimeout(() => setResetConfirm(false), 4000);
      return;
    }
    updateProfile({
      recentClusters: [],
      followedTopics: [],
      followedSources: []
    });
    setResetConfirm(false);
  };

  return (
    <div className="settings-island space-y-8">
      {/* Overview stats */}
      <section className="premium-card">
        <div className="settings-module-head mb-6">
          <div>
            <p className="settings-kicker"><Sparkles size={14} /> {t('settings.profile.reading_kicker')}</p>
            <h2 className="text-xl sm:text-2xl font-black font-serif italic mt-1">{t('settings.profile.reading_title')}</h2>
          </div>
          <p className="settings-copy mt-2 text-xs sm:text-sm text-muted-foreground leading-relaxed">
            {t('settings.profile.reading_copy')}
          </p>
        </div>

        <div className="settings-stat-grid">
          <div className="stat-glow-card">
            <span>{t('settings.profile.followed_topics')}</span>
            <strong>{followedTopics.length}</strong>
          </div>
          <div className="stat-glow-card">
            <span>{t('settings.profile.followed_sources')}</span>
            <strong>{followedSources.length}</strong>
          </div>
          <div className="stat-glow-card">
            <span>{t('settings.profile.recent')}</span>
            <strong>{(profile?.recentClusters || []).length}</strong>
          </div>
        </div>

        {topFocusTopic && (
          <div className="mt-6 p-4 bg-secondary border border-border rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
            <div>
              <p className="text-[11px] font-black uppercase text-muted-foreground tracking-widest mb-0.5">{t('settings.profile.focus_topic')}</p>
              <h4 className="font-serif font-black text-lg italic">{topFocusTopic}</h4>
            </div>
            <p className="text-[11px] text-muted-foreground leading-tight max-w-[200px]">
              {t('settings.profile.focus_topic_copy')}
            </p>
          </div>
        )}

        {/* Clear profile history / reset button */}
        <div className="mt-8 pt-6 border-t border-border/40 flex justify-end">
          <button
            type="button"
            onClick={handleResetProfile}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all duration-300 ${
              resetConfirm
                ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/20 scale-[0.98]'
                : 'bg-secondary/40 hover:bg-red-500/10 text-muted-foreground hover:text-red-500 border border-border/60 hover:border-red-500/30'
            }`}
          >
            {resetConfirm ? <Check size={14} /> : <Trash2 size={14} />}
            <span>
              {resetConfirm
                ? t('settings.profile.reset_confirm')
                : t('settings.profile.reset')}
            </span>
          </button>
        </div>
      </section>

      {/* Followed interests */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="premium-card">
          <div className="settings-module-head mb-4">
            <p className="settings-kicker"><Newspaper size={14} /> {t('settings.profile.followed_topics')}</p>
            <h3 className="text-base font-bold font-sans mt-0.5">{t('settings.profile.topics_title')}</h3>
          </div>
          {followedTopics.length > 0 ? (
            <div className="flex flex-wrap gap-2 mt-4">
              {followedTopics.map((topic: string) => (
                <div key={topic} className="settings-premium-chip">
                  <span>{topic}</span>
                  <button
                    type="button"
                    onClick={() => removeFollow('topic', topic)}
                    title={t('settings.profile.remove_topic')}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              {t('settings.profile.no_topics')}
            </p>
          )}
        </div>

        <div className="premium-card">
          <div className="settings-module-head mb-4">
            <p className="settings-kicker"><Newspaper size={14} /> {t('settings.profile.followed_sources')}</p>
            <h3 className="text-base font-bold font-sans mt-0.5">{t('settings.profile.sources_title')}</h3>
          </div>
          {followedSources.length > 0 ? (
            <div className="flex flex-wrap gap-2 mt-4">
              {followedSources.map((source: string) => (
                <div key={source} className="settings-premium-chip">
                  <span>{source}</span>
                  <button
                    type="button"
                    onClick={() => removeFollow('source', source)}
                    title={t('settings.profile.remove_source')}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              {t('settings.profile.no_sources')}
            </p>
          )}
        </div>
      </section>

      {/* Recommendations */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="premium-card">
          <div className="settings-module-head mb-4">
            <p className="settings-kicker"><Sparkles size={14} /> {t('settings.profile.topic_suggestions_kicker')}</p>
            <h3 className="text-base font-bold font-sans mt-0.5">{t('settings.profile.topic_suggestions_title')}</h3>
          </div>
          {recommendations.topics.length > 0 ? (
            <div className="space-y-2 mt-4">
              {recommendations.topics.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className="w-full flex items-center justify-between p-3 bg-secondary/30 hover:bg-secondary/60 border border-border/50 hover:border-border rounded-none transition-all text-left group"
                  onClick={() => addFollow('topic', item.value)}
                >
                  <div>
                    <span className="block font-sans font-bold text-xs uppercase tracking-wider text-foreground group-hover:text-foreground transition-colors">{item.value}</span>
                    <span className="block text-[11px] text-muted-foreground mt-0.5">{item.reason}</span>
                  </div>
                  <span className="text-xs font-black text-muted-foreground group-hover:text-foreground px-2.5 py-1 bg-secondary rounded-none group-hover:bg-muted transition-all">{t('settings.profile.follow_action')}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              {t('settings.profile.no_topic_suggestions')}
            </p>
          )}
        </div>

        <div className="premium-card">
          <div className="settings-module-head mb-4">
            <p className="settings-kicker"><Sparkles size={14} /> {t('settings.profile.source_suggestions_kicker')}</p>
            <h3 className="text-base font-bold font-sans mt-0.5">{t('settings.profile.source_suggestions_title')}</h3>
          </div>
          {recommendations.sources.length > 0 ? (
            <div className="space-y-2 mt-4">
              {recommendations.sources.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className="w-full flex items-center justify-between p-3 bg-secondary/30 hover:bg-secondary/60 border border-border/50 hover:border-border rounded-none transition-all text-left group"
                  onClick={() => addFollow('source', item.value)}
                >
                  <div>
                    <span className="block font-sans font-bold text-xs uppercase tracking-wider text-foreground group-hover:text-foreground transition-colors">{item.value}</span>
                    <span className="block text-[11px] text-muted-foreground mt-0.5">{item.reason}</span>
                  </div>
                  <span className="text-xs font-black text-muted-foreground group-hover:text-foreground px-2.5 py-1 bg-secondary rounded-none group-hover:bg-muted transition-all">{t('settings.profile.follow_action')}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
              {t('settings.profile.no_source_suggestions')}
            </p>
          )}
        </div>
      </section>

      {/* Recent history */}
      <section className="premium-card">
        <div className="settings-module-head mb-4">
          <p className="settings-kicker"><Clock3 size={14} /> {t('settings.profile.recent_kicker')}</p>
          <h3 className="text-base sm:text-lg font-bold font-sans mt-0.5">{t('settings.profile.recent_title')}</h3>
        </div>
        {recentItems.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 mt-4">
            {recentItems.map((item: any) => (
              <a
                key={item.clusterId}
                href={localePathForLang(`/cluster/${item.clusterId}`, locale)}
                className="flex items-start justify-between gap-4 p-4 bg-secondary/20 hover:bg-secondary/40 border border-border/40 hover:border-border rounded-xl transition-all group"
              >
                <div className="min-w-0">
                  <span className="inline-block text-[11px] font-black uppercase text-muted-foreground tracking-widest mb-1">{item.topic || t('settings.profile.fallback_cluster')}</span>
                  <h4 className="font-serif font-black text-sm sm:text-base leading-tight text-foreground group-hover:text-foreground transition-colors line-clamp-2">{item.title}</h4>
                  <span className="inline-block text-[11px] text-muted-foreground mt-1.5">{item.source || t('settings.profile.fallback_source')}</span>
                </div>
                <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-foreground group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all shrink-0 mt-0.5" />
              </a>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
            {t('settings.profile.no_recent')}
          </p>
        )}
      </section>
    </div>
  );
}
