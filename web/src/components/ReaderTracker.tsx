import { useEffect } from 'react';
import { recordClusterView } from '../lib/personalization.js';

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
  useEffect(() => {
    recordClusterView({
      cluster_id: clusterId,
      title,
      category,
      topic,
      primarySource,
      sources,
      tags,
      viewedAt: new Date().toISOString(),
    });
  }, [category, clusterId, primarySource, sources, tags, title, topic]);

  return null;
}
