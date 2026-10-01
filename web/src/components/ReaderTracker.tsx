import { useEffect, useRef } from 'react';
import { recordClusterView } from '../lib/personalization.js';
import { recordClusterVisit } from '../lib/homepageMode';

export default function ReaderTracker({
  clusterId,
  title,
  category,
  topic,
  primarySource,
  sources = [],
  tags = [],
}: {
  clusterId: string;
  title: string;
  category?: string;
  topic?: string;
  primarySource?: string;
  sources?: string[];
  tags?: string[];
}) {
  const payloadRef = useRef({ clusterId, title, category, topic, primarySource, sources, tags });
  payloadRef.current = { clusterId, title, category, topic, primarySource, sources, tags };

  const sourcesKey = sources.join('\u0001');
  const tagsKey = tags.join('\u0001');

  useEffect(() => {
    const p = payloadRef.current;
    recordClusterVisit();
    recordClusterView({
      cluster_id: p.clusterId,
      title: p.title,
      category: p.category,
      topic: p.topic,
      primarySource: p.primarySource,
      sources: p.sources,
      tags: p.tags,
      viewedAt: new Date().toISOString(),
    });
  }, [category, clusterId, primarySource, title, topic, sourcesKey, tagsKey]);

  return null;
}
