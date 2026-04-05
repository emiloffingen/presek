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
            <p className="settings-kicker"><Sparkles size={14} /> Вашиот профил на читање</p>
            <h2>Што Пресек памети на овој уред</h2>
          </div>
          <p className="settings-copy">
            Овие сигнали го обликуваат вашиот модул `За Вас`, изборот на известувања и неделната достава уште пред нешто да се синхронизира.
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

      <section className="settings-module">
        <div className="settings-module-head">
          <div>
            <p className="settings-kicker"><Clock3 size={14} /> Неодамнешно читање</p>
            <h3>Кластери што го обликуваа вашиот тековен профил</h3>
          </div>
        </div>
        {recentItems.length > 0 ? (
          <div className="settings-recent-list">
            {recentItems.map((item) => (
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
