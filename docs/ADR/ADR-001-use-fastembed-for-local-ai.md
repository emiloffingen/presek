# ADR-001: Use fastembed for Local AI Embeddings

## Status

Accepted

## Context

Presek needs to generate vector embeddings for:
- Article clustering (grouping similar articles)
- Semantic search (finding relevant articles based on query meaning)
- Similarity scoring (determining article relationships)

Initially, Presek relied on external AI providers (Jina AI, Cloudflare AI) for embeddings. This approach had several drawbacks:

1. **Cost**: External API calls incur per-request costs that scale with usage
2. **Latency**: Network round-trips to external services add 100-500ms per request
3. **Reliability**: Dependence on third-party services introduces potential points of failure
4. **Privacy**: Article content is sent to external services, raising data privacy concerns
5. **Rate Limits**: External services impose rate limits that can throttle ingestion

The `fastembed` library provides a compelling alternative:
- Open-source Python library for local embeddings
- Supports multilingual embeddings (including Macedonian/Serbian)
- Runs on CPU (no GPU required)
- Lightweight and fast (~10-50ms per embedding on modern hardware)
- No external API calls or costs

## Decision

**Use fastembed as the primary embedding provider with external providers as fallback.**

Implementation:
1. Integrate fastembed as the default embedding provider
2. Use `all-MiniLM-L6-v2` model for general embeddings
3. Keep external providers (Cloudflare, NVIDIA, etc.) as fallback options
4. Configure provider fallback order to prioritize local first
5. Add monitoring for embedding generation performance

## Alternatives Considered

### Alternative 1: Continue with External Providers Only

**Pros:**
- No local infrastructure to maintain
- Potentially higher quality embeddings from specialized providers
- No local resource usage

**Cons:**
- Ongoing costs that scale with usage
- Network latency for every embedding
- Privacy concerns with external data processing
- Single point of failure if provider goes down
- Rate limiting constraints

**Rejected because:** Cost and reliability concerns outweigh the benefits.

### Alternative 2: Use Sentence Transformers Directly

**Pros:**
- More model options available
- Direct control over model loading and inference

**Cons:**
- Larger memory footprint (models are larger)
- Slower initialization (models need to be loaded)
- More complex to manage multiple models
- Requires more storage space

**Rejected because:** fastembed provides a simpler, more optimized interface to the same underlying models.

### Alternative 3: Hybrid Approach (Local + External)

**Pros:**
- Best of both worlds: local for most, external for high-quality needs
- Can use local for clustering, external for synthesis

**Cons:**
- More complex architecture
- Still has some external costs
- Need to manage multiple embedding sources

**Accepted as partial solution:** This is essentially what we implemented, with local (fastembed) as primary and external as fallback.

### Alternative 4: ONNX Runtime with Distilled Models

**Pros:**
- Potentially faster inference
- Smaller model sizes

**Cons:**
- More complex setup
- Less Pythonic API
- Limited model availability

**Rejected because:** fastembed already provides good performance with a simpler API.

## Consequences

### Positive Consequences

1. **Cost Savings**: Eliminates per-request embedding costs, which were a significant portion of AI expenses
2. **Performance**: Reduces embedding generation latency from 100-500ms to 10-50ms
3. **Reliability**: Removes dependency on external services for core functionality
4. **Privacy**: Article content stays within the local infrastructure
5. **Scalability**: Can process embeddings at local hardware limits without API rate limits
6. **Offline Capability**: System can continue to function without internet connectivity for embeddings

### Negative Consequences

1. **Resource Usage**: Uses local CPU resources for embedding generation
2. **Model Quality**: Local models may be slightly lower quality than state-of-the-art external models
3. **Model Updates**: Need to manually update models to get improvements (vs. automatic with external providers)
4. **Initialization Time**: First embedding request after startup has model loading overhead
5. **Memory Usage**: Models consume RAM when loaded (~50-200MB depending on model)

### Trade-offs

| Aspect | Local (fastembed) | External Providers |
|--------|------------------|-------------------|
| Cost | Free | Paid per request |
| Latency | 10-50ms | 100-500ms |
| Privacy | ✅ Local | ❌ External |
| Reliability | ✅ Independent | ❌ Dependent |
| Quality | Good | Potentially Better |
| Scalability | Hardware-limited | Rate-limited |
| Maintenance | Self-managed | Provider-managed |

## Implementation Details

### Code Location

- `core/embeddings.py` - Main embedding generation logic
- `core/ai_engine.py` - Provider management and fallback
- `core/config.py` - Configuration for embedding providers

### Configuration

```python
# Provider fallback order (in core/config.py)
PROVIDER_FALLBACK_ORDER = ["local", "cloudflare", "nvidia", "groq"]

# Embedding-specific settings
EMBEDDING_PROVIDER = "local"  # Default to fastembed
FASTEMBEDDING_MODEL = "all-MiniLM-L6-v2"
```

### Usage Example

```python
from core.embeddings import generate_embeddings_batch, local_distance

# Generate embeddings for a batch of articles
articles = [{"title": "...", "content": "..."}, ...]
embeddings = await generate_embeddings_batch(articles)

# Calculate similarity between articles
similarity = local_distance(embedding1, embedding2)
```

### Fallback Mechanism

```python
from core.ai_engine import call_ai

# Try local first, fall back to external providers
try:
    embedding = await generate_embeddings_batch(articles, provider="local")
except Exception as e:
    log.warning(f"Local embedding failed, falling back: {e}")
    # Try next provider in fallback order
    embedding = await generate_embeddings_batch(articles, provider="cloudflare")
```

## Monitoring

Key metrics to monitor:
- Embedding generation time (p50, p90, p99)
- Embedding generation success/failure rates
- Fallback rate (how often local fails and needs external)
- Memory usage of embedding models
- CPU usage during embedding generation

## Migration Path

The migration from external to local embeddings was seamless:

1. **Phase 1**: Add fastembed as an option alongside existing providers
2. **Phase 2**: Update fallback order to prioritize local
3. **Phase 3**: Monitor performance and quality
4. **Phase 4**: Remove or de-prioritize external providers for embeddings

No data migration was needed as embeddings are regenerated as needed.

## Related Decisions

- ADR-002: Multi-Provider AI Cascade - Complements this decision by providing fallback mechanism
- ADR-003: Privacy-First Analytics - Aligns with the privacy benefits of local processing

## References

- [fastembed GitHub Repository](https://github.com/qdrant/fastembed)
- [fastembed Documentation](https://qdrant.github.io/fastembed/)
- [Hugging Face Sentence Transformers](https://www.sentence-transformers.net/)
- [Presek Embeddings Module](core/embeddings.py)
- [Presek AI Engine](core/ai_engine.py)
