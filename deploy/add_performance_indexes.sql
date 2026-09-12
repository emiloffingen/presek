-- Performance Optimization Indexes for Presek
-- Run this on your PostgreSQL database to improve query performance
-- These indexes address N+1 query problems and enable efficient vector search

-- ============================================================================
-- 1. pgvector IVFFlat Indexes (HIGHEST IMPACT)
-- Enable fast approximate nearest neighbor search for clustering and semantic search
-- ============================================================================

-- Index for cluster centroid vector search (used in clustering.py find_cluster_semantic)
CREATE INDEX IF NOT EXISTS idx_cluster_metadata_centroid
ON cluster_metadata USING ivfflat (centroid vector_l2_ops)
WITH (lists = 100);

-- Index for article embedding vector search (used in semantic search)
CREATE INDEX IF NOT EXISTS idx_articles_embedding
ON articles USING ivfflat (embedding vector_l2_ops)
WITH (lists = 200);

-- ============================================================================
-- 2. Composite B-Tree Indexes for Common Query Patterns
-- ============================================================================

-- For cluster-based article queries (routes/news.py, core/clustering.py)
CREATE INDEX IF NOT EXISTS idx_articles_cluster_id_created_at
ON articles (cluster_id, created_at DESC);

-- For category filtering (routes/news.py, routes/home.py)
CREATE INDEX IF NOT EXISTS idx_articles_category_created_at
ON articles (category, created_at DESC);

-- For source-based queries
CREATE INDEX IF NOT EXISTS idx_articles_source_created_at
ON articles (source, created_at DESC);

-- For is_global filtering (routes/home.py)
CREATE INDEX IF NOT EXISTS idx_articles_is_global_created_at
ON articles (is_global, created_at DESC);

-- For topic filtering
CREATE INDEX IF NOT EXISTS idx_articles_topic_created_at
ON articles (topic, created_at DESC);

-- ============================================================================
-- 3. Full-Text Search Indexes
-- ============================================================================

-- GIN index for full-text search vector (used in hybrid search)
CREATE INDEX IF NOT EXISTS idx_articles_search_vector_gin
ON articles USING gin(search_vector);

-- ============================================================================
-- 4. Timestamp Indexes for Time-Based Filtering
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_articles_created_at_desc
ON articles (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_ingested_at_desc
ON articles (ingested_at DESC);

-- ============================================================================
-- 5. Cluster Metadata Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_cluster_metadata_updated_at_desc
ON cluster_metadata (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cluster_metadata_category
ON cluster_metadata (category);

-- ============================================================================
-- 6. Storyline Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_storylines_v2_created_at
ON storylines_v2 (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_storyline_clusters_v2_storyline_id
ON storyline_clusters_v2 (storyline_id);

CREATE INDEX IF NOT EXISTS idx_storyline_clusters_v2_cluster_id
ON storyline_clusters_v2 (cluster_id);

-- ============================================================================
-- 7. Update Statistics
-- ============================================================================

VACUUM ANALYZE articles;
VACUUM ANALYZE cluster_metadata;
VACUUM ANALYZE storylines_v2;
VACUUM ANALYZE storyline_clusters_v2;

-- ============================================================================
-- 8. Verification Query
-- ============================================================================

-- Run this to verify all indexes were created
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('articles', 'cluster_metadata', 'storylines_v2', 'storyline_clusters_v2')
ORDER BY tablename, indexname;
