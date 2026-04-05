import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Clock3, Newspaper, Sparkles, X } from 'lucide-react';
import { loadReaderProfile, toggleFollowedValue } from '../lib/personalization.js';

function summarizeRecent(profile: any) {
  const recent = Array.isArray(profile?.recentClusters) ? profile.recentClusters : [];
  return recent.slice(0, 5).map((item) => ({
    clusterId: String(item?.cluster_id || '').trim(),
    title: String(item?.title || '').trim(),
    topic: String(item?.topic || item?.category || '').trim(),
    source: String(item?.primarySource || '').trim(),
  })).filter((item) => item.clusterId && item.title);
}

export default function SettingsProfileIsland() {
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    setProfile(loadReaderProfile());
  }, []);

  const followedTopics = useMemo(() => profile?.followedTopics || [], [profile]);
  const followedSources = useMemo(() => profile?.followedSources || [], [profile]);
  const recentItems = useMemo(() => summarizeRecent(profile), [profile]);

  const removeFollow = (kind: 'topic' | 'source', value: string) => {
    const result = toggleFollowedValue(kind, value);
    setProfile(result.profile);
  };

  return (
    <div className="settings-island">
      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Sparkles size={14} /> Your reading profile</p>
            <h2>What Presek remembers on this device</h2>
          </div>
          <p className="settings-copy">
            These signals shape your `For You` module, alert matching, and weekly delivery before anything is synced.
          </p>
        </div>

        <div className="settings-stat-grid">
          <div className="settings-stat-card">
            <span>Followed topics</span>
            <strong>{followedTopics.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Followed sources</span>
            <strong>{followedSources.length}</strong>
          </div>
          <div className="settings-stat-card">
            <span>Recent clusters</span>
            <strong>{(profile?.recentClusters || []).length}</strong>
          </div>
        </div>
      </section>

      <section className="settings-grid">
        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Followed topics</p>
              <h3>Topics you want surfaced faster</h3>
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
            <p className="settings-empty">No followed topics yet. Follow a topic from a topic page to make delivery and ranking more personal.</p>
          )}
        </div>

        <div className="settings-module">
          <div className="settings-module-head">
            <div>
              <p className="settings-kicker"><Newspaper size={14} /> Followed sources</p>
              <h3>Sources you want watched closely</h3>
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
            <p className="settings-empty">No followed sources yet. Follow a lead source from a cluster page to receive source-specific updates.</p>
          )}
        </div>
      </section>

      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Clock3 size={14} /> Recent reading</p>
            <h3>Clusters that shaped your current profile</h3>
          </div>
        </div>
        {recentItems.length > 0 ? (
          <div className="settings-recent-list">
            {recentItems.map((item) => (
              <a key={item.clusterId} href={`/cluster/${item.clusterId}`} className="settings-recent-item">
                <div>
                  <p className="settings-recent-topic">{item.topic || 'Cluster'}</p>
                  <h4>{item.title}</h4>
                  <p className="settings-recent-source">{item.source || 'Source'}</p>
                </div>
                <ArrowUpRight size={14} />
              </a>
            ))}
          </div>
        ) : (
          <p className="settings-empty">Open a few clusters and this page will start explaining what drives your personalization and delivery.</p>
        )}
      </section>
    </div>
  );
}
