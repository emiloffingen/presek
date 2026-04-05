import React, { useEffect, useState } from 'react';
import { ArrowUpRight, Compass, Sparkles } from 'lucide-react';
import { buildPersonalizedClusters, hasPersonalizationSignal, loadReaderProfile } from '../lib/personalization.js';

function getSummary(cluster: any) {
  const article = cluster?.articles?.[0];
  const text = article?.summary || article?.description || '';
  return String(text).replace(/\s+/g, ' ').trim();
}

export default function ForYouIsland({ clusters = [] }: { clusters?: any[] }) {
  const [items, setItems] = useState<any[]>([]);
  const [hasSignals, setHasSignals] = useState(false);

  useEffect(() => {
    const profile = loadReaderProfile();
    const nextHasSignals = hasPersonalizationSignal(profile);
    setHasSignals(nextHasSignals);
    if (!nextHasSignals) {
      setItems([]);
      return;
    }
    setItems(buildPersonalizedClusters(clusters, profile, 4));
  }, [clusters]);

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
    </section>
  );
}

