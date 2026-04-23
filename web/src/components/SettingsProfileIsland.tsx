import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Clock3, Newspaper, Sparkles, X } from 'lucide-react';
import {
  buildSurfaceFollowSuggestions,
  loadReaderProfile,
  recordSuggestionFollow,
  recordSuggestionImpressions,
  saveReaderProfile,
  sendSuggestionEvents,
  subscribeToReaderProfile,
  toggleFollowedValue,
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

export default function SettingsProfileIsland() {
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    return subscribeToReaderProfile(setProfile);
  }, []);

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

        const nextProfile = {
          ...profile,
          recentClusters: (profile?.recentClusters || []).filter((item: any) => !invalidIds.has(String(item?.cluster_id || '').trim())),
        };
        const saved = saveReaderProfile(nextProfile);
        setProfile(saved);
      } catch {
        // Ignore cleanup failures; they should not block the settings view.
      }
    };

    validateRecent();
    return () => {
      cancelled = true;
    };
  }, [profile]);

  const followedTopics = useMemo(() => profile?.followedTopics || [], [profile]);
  const followedSources = useMemo(() => profile?.followedSources || [], [profile]);
  const recentItems = useMemo(() => summarizeRecent(profile), [profile]);
  
  const topFocusTopic = useMemo(() => {
    if (recentItems.length === 0) return null;
    const counts: Record<string, number> = {};
    recentItems.forEach((item: any) => {
        const t = item.topic || 'Вести';
        counts[t] = (counts[t] || 0) + 1;
    });
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return entries.length > 0 ? entries[0][0] : null;
  }, [recentItems]);

  const recommendations = useMemo(
    () => buildSurfaceFollowSuggestions(profile, 'settings', { topicLimit: 3, sourceLimit: 2 }),
    [profile]
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
    const result = toggleFollowedValue(kind, value);
    setProfile(result.profile);
  };

  const addFollow = (kind: 'topic' | 'source', value: string) => {
    const result = toggleFollowedValue(kind, value);
    if (result.isFollowing) {
      const tracked = recordSuggestionFollow('settings', kind, value);
      if (tracked.recorded) {
        sendSuggestionEvents([{ surface: 'settings', eventType: 'follow', suggestionKind: kind, value }]);
      }
    }
    setProfile(result.profile);
  };

  return (
    <div className="settings-island">
      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Sparkles size={14} /> Вашиот профил на читање</p>
            <h2>Што Пресек памети на овој уред</h2>
          </div>
          <p className="settings-copy">
            Овие сигнали го обликуваат вашиот модул „За Вас“, изборот на известувања и неделната достава уште пред нешто да се синхронизира.
          </p>
        </div>

        <div className="settings-stat-grid">
          <div className="settings-stat-card">
            <span>Следени теми</span>
            <strong>{followedTopics.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Следени извори</span>
            <strong>{followedSources.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Неодамнешни кластери</span>
            <strong>{(profile?.recentClusters || []).length}</strong>
          </div>
        </div>

        {topFocusTopic && (
            <div className="mt-8 p-4 bg-nyt-accent/5 border border-nyt-accent/20 rounded-lg flex items-center justify-between">
                <div>
                    <p className="text-[10px] font-black uppercase text-nyt-accent tracking-widest mb-1">Вашиот примарен фокус</p>
                    <h4 className="font-serif font-black text-xl italic">{topFocusTopic}</h4>
                </div>
                <div className="text-right">
                    <p className="text-[10px] font-bold text-muted-foreground leading-tight">Врз основа на последното читање.<br/>Го користиме за „За Вас“.</p>
                </div>
            </div>
        )}
      </section>

      <section className="settings-grid">
        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Следени теми</p>
              <h3>Теми што сакате да излегуваат побрзо</h3>
            </div>
          </div>
          {followedTopics.length > 0 ? (
            <div className="settings-chip-list">
              {followedTopics.map((topic: string) => (
                <button
                  key={topic}
                  type="button"
                  className="settings-chip"
                  onClick={() => removeFollow('topic', topic)}
                >
                  <span>{topic}</span>
                  <X size={12} />
                </button>
              ))}
            </div>
          ) : (
            <p className="settings-empty">Сè уште немате следени теми. Следете тема од страницата за теми за доставата и рангирањето да станат полични.</p>
          )}
        </div>

        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Следени извори</p>
              <h3>Извори што сакате внимателно да се следат</h3>
            </div>
          </div>
          {followedSources.length > 0 ? (
            <div className="settings-chip-list">
              {followedSources.map((source: string) => (
                <button
                  key={source}
                  type="button"
                  className="settings-chip"
                  onClick={() => removeFollow('source', source)}
                >
                  <span>{source}</span>
                  <X size={12} />
                </button>
              ))}
            </div>
          ) : (
            <p className="settings-empty">Сè уште немате следени извори. Следете водечки извор од кластер страница за да добивате извор-специфични ажурирања.</p>
          )}
        </div>
      </section>

      <section className="settings-grid">
        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Sparkles size={14} /> Предлози за теми</p>
              <h3>Што вреди да следите следно</h3>
            </div>
          </div>
          {recommendations.topics.length > 0 ? (
            <div className="settings-suggestion-list">
              {recommendations.topics.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className="settings-suggestion"
                  onClick={() => addFollow('topic', item.value)}
                >
                  <span className="settings-suggestion-value">{item.value}</span>
                  <span className="settings-suggestion-reason">{item.reason}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="settings-empty">Кога ќе прочитате уште неколку кластери, тука ќе се појават теми што има смисла да ги следите.</p>
          )}
        </div>

        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Sparkles size={14} /> Предлози за извори</p>
              <h3>Извори што веќе се вклопуваат во вашето читање</h3>
            </div>
          </div>
          {recommendations.sources.length > 0 ? (
            <div className="settings-suggestion-list">
              {recommendations.sources.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className="settings-suggestion"
                  onClick={() => addFollow('source', item.value)}
                >
                  <span className="settings-suggestion-value">{item.value}</span>
                  <span className="settings-suggestion-reason">{item.reason}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="settings-empty">Кога ќе се појават повторливи извори во вашето читање, тука ќе добиете брзи предлози за следење.</p>
          )}
        </div>
      </section>

      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Clock3 size={14} /> Неодамнешно читање</p>
            <h3>Кластери што го обликуваа вашиот тековен профил</h3>
          </div>
        </div>
        {recentItems.length > 0 ? (
          <div className="settings-recent-list">
            {recentItems.map((item: any) => (
              <a key={item.clusterId} href={`/cluster/${item.clusterId}`} className="settings-recent-item">
                <div>
                  <p className="settings-recent-topic">{item.topic || 'Кластер'}</p>
                  <h4>{item.title}</h4>
                  <p className="settings-recent-source">{item.source || 'Извор'}</p>
                </div>
                <ArrowUpRight size={14} />
              </a>
            ))}
          </div>
        ) : (
          <p className="settings-empty">Отворете неколку кластери и оваа страница ќе почне да објаснува што ги движи вашата персонализација и достава.</p>
        )}
      </section>
    </div>
  );
}
