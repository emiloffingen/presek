function normalize(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function unique(values) {
  return Array.from(new Set((Array.isArray(values) ? values : []).map((value) => normalize(value)).filter(Boolean)));
}

export function buildTopicConnections(currentTopic, clusters = [], details = [], limit = 5) {
  const current = normalize(currentTopic).toLowerCase();
  if (!current) return [];

  const currentSources = new Set(
    clusters.flatMap((cluster) => (cluster?.articles || []).map((article) => normalize(article?.source)).filter(Boolean))
  );
  const currentTags = new Set(
    details.flatMap((detail) => unique(detail?.tags || [])).filter((tag) => normalize(tag).toLowerCase() !== current)
  );

  const topicMap = new Map();

  details.forEach((detail, index) => {
    const cluster = clusters[index] || {};
    const visibleClusterTopics = new Set(unique((cluster?.articles || []).map((article) => article?.topic)));
    const detailTopics = unique(detail?.topics || []).filter(
      (topic) => visibleClusterTopics.size === 0 || visibleClusterTopics.has(topic)
    );
    const detailTags = unique(detail?.tags || []);
    const clusterSources = unique((cluster?.articles || []).map((article) => article?.source));
    const sharedSourceCount = clusterSources.filter((source) => currentSources.has(source)).length;
    const sharedTagCount = detailTags.filter((tag) => currentTags.has(tag)).length;

    detailTopics.forEach((topic) => {
      const normalizedTopic = normalize(topic);
      if (!normalizedTopic || normalizedTopic.toLowerCase() === current) return;

      const entry = topicMap.get(normalizedTopic) || {
        topic: normalizedTopic,
        clusterCount: 0,
        breakingCount: 0,
        sharedSourceCount: 0,
        sharedTagCount: 0,
        tags: new Set(),
      };

      entry.clusterCount += 1;
      if (cluster?.is_breaking) entry.breakingCount += 1;
      entry.sharedSourceCount += sharedSourceCount;
      entry.sharedTagCount += sharedTagCount;
      detailTags.forEach((tag) => {
        const cleanTag = normalize(tag);
        if (cleanTag && cleanTag.toLowerCase() !== current) {
          entry.tags.add(cleanTag);
        }
      });

      topicMap.set(normalizedTopic, entry);
    });
  });

  const ranked = Array.from(topicMap.values())
    .map((entry) => {
      const score =
        entry.clusterCount * 1.2 +
        entry.breakingCount * 1.15 +
        entry.sharedTagCount * 0.38 +
        entry.sharedSourceCount * 0.26;

      let relationshipLabel = 'Поврзана тема';
      let relationshipNote = `${entry.clusterCount} кластери веќе се прелеваат од ${currentTopic} кон ${entry.topic}.`;

      if (entry.breakingCount >= 2) {
        relationshipLabel = 'Следна развојна линија';
        relationshipNote = `${entry.topic} станува следниот фронт на приказната, со ${entry.breakingCount} активни развои што се надоврзуваат на ${currentTopic}.`;
      } else if (entry.sharedTagCount >= 3) {
        relationshipLabel = 'Поширока рамка';
        relationshipNote = `${entry.topic} ја шири истата приказна преку исти имиња и агли, не само преку површна тематска блискост.`;
      } else if (entry.sharedSourceCount >= 3) {
        relationshipLabel = 'Истите актери, друг фронт';
        relationshipNote = `${entry.topic} ја следат многу од истите редакции и извори што го туркаат и ${currentTopic}, но со поинаква последица или арена.`;
      }

      return {
        topic: entry.topic,
        score,
        clusterCount: entry.clusterCount,
        breakingCount: entry.breakingCount,
        sharedSourceCount: entry.sharedSourceCount,
        sharedTagCount: entry.sharedTagCount,
        sampleTags: Array.from(entry.tags).slice(0, 3),
        relationshipLabel,
        relationshipNote,
      };
    })
    .sort((left, right) => right.score - left.score);

  return ranked.slice(0, limit);
}
