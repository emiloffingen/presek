import React, { useEffect, useState } from 'react';
import { ArrowUpRight, Compass, Sparkles } from 'lucide-react';
import PreferenceToggle from './PreferenceToggle.tsx';
import {
  buildFollowRecommendations,
  buildPersonalizedClusters,
  hasPersonalizationSignal,
  loadReaderProfile,
} from '../lib/personalization.js';

function getSummary(cluster: any) {
  const article = cluster?.articles?.[0];
  const text = article?.summary || article?.description || '';
  return String(text).replace(/\s+/g, ' ').trim();
}

export default function ForYouIsland({ clusters = [] }: { clusters?: any[] }) {
  const [items, setItems] = useState<any[]>([]);
  const [hasSignals, setHasSignals] = useState(false);
  const [profile, setProfile] = useState(() => loadReaderProfile());

  useEffect(() => {
    const profile = loadReaderProfile();
    setProfile(profile);
    const nextHasSignals = hasPersonalizationSignal(profile);
    setHasSignals(nextHasSignals);
    if (!nextHasSignals) {
      setItems([]);
      return;
    }
    setItems(buildPersonalizedClusters(clusters, profile, 4));
  }, [clusters]);

  const recommendations = buildFollowRecommendations(profile, 2);

  if (!hasSignals || items.length === 0) {
    return null;
  }

  return (
    <section className="for-you-module">
      <div className="for-you-head">
        <div>
          <p className="for-you-kicker"><Sparkles size={14} /> За Вас</p>
          <h2>Патека според тоа што веќе следите</h2>
        </div>
        <p className="for-you-note">
          Избрано од вашите следени теми, омилени извори и неодамнешно читање на овој уред.
        </p>
      </div>

      <div className="for-you-grid">
        {items.map((item) => {
          const cluster = item.cluster;
          const article = cluster.articles?.[0] || {};
          const summary = getSummary(cluster);
          return (
            <a key={cluster.cluster_id} href={`/cluster/${cluster.cluster_id}`} className="for-you-card">
              <p className="for-you-card-kicker">
                <Compass size={12} />
                <span>{item.reason || 'Поврзано со вашето читање'}</span>
              </p>
              <h3>{article.title || 'Кластер'}</h3>
              {summary && <p className="for-you-card-copy">{summary}</p>}
              <div className="for-you-card-meta">
                <span>{article.source || 'Извор'}</span>
                <span>·</span>
                <span>{cluster.articles?.length || 0} извори</span>
              </div>
              <span className="for-you-card-cta">Отвори кластер <ArrowUpRight size={12} /></span>
            </a>
          );
        })}
      </div>

      {(recommendations.topics.length > 0 || recommendations.sources.length > 0) && (
        <div className="for-you-follow-block">
          <div className="for-you-follow-head">
            <p className="for-you-kicker"><Sparkles size={14} /> Следете го следното</p>
            <p className="for-you-note">
              Овие теми и извори се појавуваат во препораките што веќе ви одговараат.
            </p>
          </div>

          <div className="for-you-follow-grid">
            {recommendations.topics.map((item) => (
              <div key={`topic:${item.value}`} className="for-you-follow-card">
                <div>
                  <p className="for-you-follow-kicker">Тема</p>
                  <strong>{item.value}</strong>
                  <p>{item.reason}</p>
                </div>
                <PreferenceToggle
                  kind="topic"
                  value={item.value}
                  label={`тема: ${item.value}`}
                  onChanged={() => setProfile(loadReaderProfile())}
                />
              </div>
            ))}

            {recommendations.sources.map((item) => (
              <div key={`source:${item.value}`} className="for-you-follow-card">
                <div>
                  <p className="for-you-follow-kicker">Извор</p>
                  <strong>{item.value}</strong>
                  <p>{item.reason}</p>
                </div>
                <PreferenceToggle
                  kind="source"
                  value={item.value}
                  label={`извор: ${item.value}`}
                  onChanged={() => setProfile(loadReaderProfile())}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
