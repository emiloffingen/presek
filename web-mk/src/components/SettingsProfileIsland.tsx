import React, { useEffect, useMemo } from 'react';
import { ArrowUpRight, Clock3, Newspaper, Sparkles, X } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $profile, updateProfile } from '../lib/store.ts';
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

export default function SettingsProfileIsland() {
  const profile = useStore($profile);

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

  return (
    <div className="settings-island">
      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Sparkles size={14} /> Vaš profil čitanja</p>
            <h2>Šta Presek pami na ovom uređaju</h2>
          </div>
          <p className="settings-copy">
            Ovi signali oblikuju vaš „Za Vas“ modul, izbor izveštaja i nedeljnju dostavu još pre sinhronizacije.
          </p>
        </div>

        <div className="settings-stat-grid">
          <div className="settings-stat-card">
            <span>Praćene teme</span>
            <strong>{followedTopics.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Praćeni izvori</span>
            <strong>{followedSources.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Nedavni klasteri</span>
            <strong>{(profile?.recentClusters || []).length}</strong>
          </div>
        </div>

        {topFocusTopic && (
            <div className="mt-8 p-4 bg-nyt-accent/5 border border-nyt-accent/20 rounded-lg flex items-center justify-between">
                <div>
                    <p className="text-[10px] font-black uppercase text-nyt-accent tracking-widest mb-1">Vaša primarna fokus tema</p>
                    <h4 className="font-serif font-black text-xl italic">{topFocusTopic}</h4>
                </div>
                <div className="text-right">
                    <p className="text-[10px] font-bold text-muted-foreground leading-tight">Na osnovu poslednjeg čitanja.<br/>Koristimo ga za „Za Vas“.</p>
                </div>
            </div>
        )}
      </section>

      <section className="settings-grid">
        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Praćene teme</p>
              <h3>Teme koje želite da se pojavljuju brže</h3>
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
            <p className="settings-empty">još uvek nemate praćene teme. Pratite temu sa strane za teme da biste dobili personalizovanu dostavu i rangiranje.</p>
          )}
        </div>

        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Praćeni izvori</p>
              <h3>izvori koje želite pažljivije da pratite</h3>
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
            <p className="settings-empty">još uvek nemate praćene izvore. Pratite vodeći izvor sa stranice klastera da biste dobijali ažuriranja specifična za izvor.</p>
          )}
        </div>
      </section>

      <section className="settings-grid">
        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Sparkles size={14} /> Predlozi za teme</p>
              <h3>Šta vredno sledeće pratite</h3>
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
            <p className="settings-empty">Kad pročitate još nekoliko klastera, ovde će se pojaviti teme koje ima smisla da pratite.</p>
          )}
        </div>

        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Sparkles size={14} /> Predlozi za izvore</p>
              <h3>izvori koji se već uklapaju u vaše čitanje</h3>
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
            <p className="settings-empty">Kad se pojave ponavljajući izvori u vašem čitanju, ovde ćete dobiti brze predloge za praćenje.</p>
          )}
        </div>
      </section>

      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Clock3 size={14} /> Nedavno čitanje</p>
            <h3>klasteri koji oblikuju vaš trenutni profil</h3>
          </div>
        </div>
        {recentItems.length > 0 ? (
          <div className="settings-recent-list">
            {recentItems.map((item: any) => (
              <a key={item.clusterId} href={`/cluster/${item.clusterId}`} className="settings-recent-item">
                <div>
                  <p className="settings-recent-topic">{item.topic || 'klaster'}</p>
                  <h4>{item.title}</h4>
                  <p className="settings-recent-source">{item.source || 'izvor'}</p>
                </div>
                <ArrowUpRight size={14} />
              </a>
            ))}
          </div>
        ) : (
          <p className="settings-empty">Otvorite nekoliko klastera i ova stranica će početi da objašnjava što pokreće vašu personalizaciju i dostavu.</p>
        )}
      </section>
    </div>
  );
}
