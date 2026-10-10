# ADR-002: Multi-Provider AI Cascade with Automatic Fallback

## Status

Accepted

## Context

Presek uses AI providers for various tasks:
- Article summarization
- Cluster synthesis
- Text generation
- Embeddings (see ADR-001)

Different AI providers have different strengths:
- **Local (fastembed, llama-cpp)**: Free, fast, private, but limited capability
- **Cloudflare AI**: Fast, cost-effective, good for many tasks
- **NVIDIA**: High quality, good for complex tasks
- **Groq**: Very fast, good for simple tasks
- **Gemini**: High quality, good for reasoning tasks
- **OpenRouter**: Access to many models, metered billing

The problem: No single provider is optimal for all tasks. Providers can:
- Have different strengths for different tasks
- Experience outages or rate limits
- Change pricing or availability
- Have different quality levels

A single-provider approach creates a single point of failure and may not provide the best quality/cost tradeoff for all use cases.

## Decision

**Implement a multi-provider cascade system with automatic fallback.**

Implementation:
1. Define provider capabilities (which tasks each provider can handle)
2. Create a priority order for each task type (summarization, synthesis, embeddings, etc.)
3. Automatically fall back to the next provider when one fails
4. Track provider performance and health
5. Allow dynamic reordering based on recent success rates

### Provider Fallback Order

```python
# Default fallback order for general AI tasks
PROVIDER_FALLBACK_ORDER = [
    "local",      # Try local first (free, fast)
    "cloudflare", # Cloudflare AI (cost-effective)
    "nvidia",     # NVIDIA (high quality)
    "groq",       # Groq (very fast)
    "gemini",     # Google Gemini (reasoning)
    "openrouter", # OpenRouter (many models)
]

# Task-specific fallback orders
PROVIDER_FALLBACK_ORDER_SUMMARY = [
    "local",
    "cloudflare",
    "nvidia",
    "groq",
]

PROVIDER_FALLBACK_ORDER_SYNTHESIS = [
    "local",
    "nvidia",
    "cloudflare",
    "gemini",
]

PROVIDER_FALLBACK_ORDER_EMBEDDINGS = [
    "local",  # fastembed - see ADR-001
    "cloudflare",
    "nvidia",
]
```

### Cascade Logic

```python
async def call_ai(prompt: str, task_type: str = "general", **kwargs) -> Optional[str]:
    """Call AI with automatic provider fallback."""

    # Get the appropriate fallback order for this task type
    providers = get_provider_fallback_order(task_type)

    last_exception = None

    for provider_name in providers:
        if not _provider_configured(provider_name):
            continue  # Skip providers without credentials

        if _provider_on_cooldown(provider_name):
            continue  # Skip rate-limited providers

        try:
            provider = PROVIDERS[provider_name]
            result = await provider.generate(prompt, **kwargs)
            _record_success(provider_name, task_type)
            return result
        except ProviderRateLimitError as e:
            _mark_provider_cooldown(provider_name, e.retry_after)
            _record_failure(provider_name, task_type, "rate_limit")
            last_exception = e
        except ProviderError as e:
            _record_failure(provider_name, task_type, str(e))
            last_exception = e

    # All providers failed
    log.error(f"All providers failed for task {task_type}: {last_exception}")
    return None
```

## Alternatives Considered

### Alternative 1: Single Primary Provider with Manual Fallback

**Pros:**
- Simpler implementation
- Easier to monitor and debug
- Consistent behavior

**Cons:**
- Single point of failure
- Manual intervention required when primary fails
- May not use the best provider for each task

**Rejected because:** Automated fallback provides better reliability without manual intervention.

### Alternative 2: Random Provider Selection

**Pros:**
- Load balancing across providers
- No single provider bottleneck

**Cons:**
- Inconsistent results (different providers give different answers)
- No preference for better providers
- Harder to debug

**Rejected because:** We want consistent, predictable behavior with preference for better providers.

### Alternative 3: Load-Based Routing

**Pros:**
- Distributes load evenly
- Can optimize for cost or performance

**Cons:**
- Complex to implement
- Requires real-time load monitoring
- May still hit rate limits

**Rejected because:** The cascade with fallback is simpler and more reliable.

### Alternative 4: Provider-Specific Endpoints

**Pros:**
- Explicit control over which provider to use
- Users can choose their preference

**Cons:**
- Exposes implementation details to users
- More complex API
- Users need to understand provider differences

**Rejected because:** We want to abstract provider selection from users.

## Consequences

### Positive Consequences

1. **Reliability**: System continues to function even when some providers are down
2. **Quality**: Can use the best provider for each task type
3. **Cost Optimization**: Can prioritize cheaper providers for suitable tasks
4. **Performance**: Can use faster providers for time-sensitive tasks
5. **Flexibility**: Easy to add new providers or change priorities
6. **Graceful Degradation**: System degrades gracefully rather than failing completely

### Negative Consequences

1. **Complexity**: More complex code to manage multiple providers
2. **Inconsistency**: Different providers may give different results for the same input
3. **Testing**: More providers to test and maintain
4. **Configuration**: More configuration options to manage
5. **Cost Tracking**: Harder to track costs across multiple providers

### Trade-offs

| Aspect | Single Provider | Multi-Provider Cascade |
|--------|----------------|------------------------|
| Reliability | ❌ Single point of failure | ✅ Automatic fallback |
| Quality | ⚠️ One size fits all | ✅ Best provider per task |
| Cost | ⚠️ May overpay | ✅ Optimize per task |
| Complexity | ✅ Simple | ❌ More complex |
| Consistency | ✅ Predictable | ⚠️ May vary by provider |
| Maintenance | ✅ Less | ❌ More |

## Implementation Details

### Code Location

- `core/ai_engine.py` - Main AI provider implementations and cascade logic
- `core/config.py` - Provider configuration and fallback orders
- `core/llm_router.py` - Provider routing and selection

### Provider Interface

All providers implement a common interface:

```python
from abc import ABC, abstractmethod
from typing import Any, Optional

class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def api_key(self) -> Optional[str]:
        """API key for this provider."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs: Any
    ) -> str:
        """Generate text from a prompt."""
        pass

    @abstractmethod
    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embeddings for text."""
        pass
```

### Provider Implementations

```python
class LocalProvider(AIProvider):
    """Local AI provider using fastembed and llama-cpp."""

    @property
    def name(self) -> str:
        return "local"

    @property
    def api_key(self) -> Optional[str]:
        return None  # No API key needed

    async def generate(self, prompt: str, **kwargs) -> str:
        # Use local models
        pass

    async def embed(self, text: str, **kwargs) -> list[float]:
        # Use fastembed
        pass


class CloudflareProvider(AIProvider):
    """Cloudflare AI provider."""

    @property
    def name(self) -> str:
        return "cloudflare"

    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get("CLOUDFLARE_API_TOKEN")

    async def generate(self, prompt: str, **kwargs) -> str:
        # Call Cloudflare AI API
        pass
```

### Provider Health Tracking

```python
# Track provider success/failure rates
_PROVIDER_STATS: dict[str, dict[str, int]] = defaultdict(
    lambda: {"success": 0, "failure": 0, "rate_limit": 0}
)

# Track cooldown periods for rate-limited providers
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}

def _record_provider_outcome(
    provider_name: str,
    task_type: str,
    success: bool,
    duration: float,
    error_type: Optional[str] = None
) -> None:
    """Record provider outcome for monitoring."""
    if success:
        _PROVIDER_STATS[provider_name]["success"] += 1
    else:
        if error_type == "rate_limit":
            _PROVIDER_STATS[provider_name]["rate_limit"] += 1
        else:
            _PROVIDER_STATS[provider_name]["failure"] += 1

    # Log metrics
    log.info(
        f"Provider {provider_name} for {task_type}: "
        f"success={success}, duration={duration:.2f}s, error={error_type}"
    )
```

## Monitoring and Metrics

Key metrics to monitor:

```python
# Prometheus metrics for AI providers
AI_GENERATION_TOTAL = Counter(
    "presek_ai_generation_total",
    "Total AI generation requests",
    ["provider", "task_type", "status"]  # status: success, failure, rate_limit
)

AI_GENERATION_DURATION = Histogram(
    "presek_ai_generation_duration_seconds",
    "AI generation duration",
    ["provider", "task_type"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
)

AI_FALLBACK_COUNT = Counter(
    "presek_ai_fallback_count",
    "Number of times fallback was used",
    ["from_provider", "to_provider", "task_type"]
)
```

### Alerts

Configure alerts for:
- High fallback rates (indicates primary provider issues)
- High failure rates for any provider
- Long generation times (p99 > 5 seconds)
- Rate limit errors

## Configuration

```python
# Environment variables for provider configuration (example values)
CLOUDFLARE_API_TOKEN="<your-cloudflare-token>"
NVIDIA_API_KEY="<your-nvidia-key>"
GROQ_API_KEY="<your-groq-key>"
GEMINI_API_KEY="<your-gemini-key>"
OPENROUTER_API_KEY="<your-openrouter-key>"

# Provider fallback orders (can be customized)
PROVIDER_FALLBACK_ORDER="local,cloudflare,nvidia"
PROVIDER_FALLBACK_ORDER_SYNTHESIS="local,nvidia,cloudflare,gemini"
PROVIDER_FALLBACK_ORDER_EMBEDDINGS="local,cloudflare"

# Provider-specific settings
CLOUDFLARE_AI_MODEL="@cf/mistral/mistral-7b-instruct"
NVIDIA_MODEL="mistralai/mistral-7b-instruct-v0.2"
GROQ_MODEL="llama3-8b-8192"
GEMINI_MODEL="gemini-1.5-flash"
```

## Testing

Test the cascade with:

```python
import pytest
from unittest.mock import AsyncMock, patch
from core.ai_engine import call_ai


@pytest.mark.asyncio
async def test_cascade_fallback_on_failure():
    """Test that cascade falls back to next provider on failure."""

    with patch("core.ai_engine.PROVIDERS") as mock_providers:
        # Mock local provider to fail
        mock_local = AsyncMock()
        mock_local.name = "local"
        mock_local.generate = AsyncMock(side_effect=Exception("Local failed"))

        # Mock cloudflare provider to succeed
        mock_cloudflare = AsyncMock()
        mock_cloudflare.name = "cloudflare"
        mock_cloudflare.generate = AsyncMock(return_value="Success")

        mock_providers.__getitem__ = {
            "local": mock_local,
            "cloudflare": mock_cloudflare,
        }.get

        result = await call_ai("test prompt")

        assert result == "Success"
        mock_local.generate.assert_called_once()
        mock_cloudflare.generate.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_respects_task_specific_order():
    """Test that cascade uses task-specific fallback order."""
    pass  # Implementation test
```

## Migration Path

The cascade system was implemented incrementally:

1. **Phase 1**: Add provider abstraction layer
2. **Phase 2**: Implement individual providers
3. **Phase 3**: Add cascade logic with fallback
4. **Phase 4**: Add monitoring and metrics
5. **Phase 5**: Add dynamic reordering based on health

No breaking changes were required as the API remained the same.

## Related Decisions

- **ADR-001: Use fastembed for Local AI Embeddings** - Provides the local provider for embeddings
- **ADR-003: Privacy-First Analytics** - Benefits from local processing capability
- **ADR-004: AI Quota Management** - Complements cascade with rate limiting

## References

- [Cloudflare AI Documentation](https://developers.cloudflare.com/workers-ai/)
- [NVIDIA AI Foundation Models](https://www.nvidia.com/en-us/ai-data-science/foundation-models/)
- [Groq API Documentation](https://console.groq.com/docs)
- [Google Gemini Documentation](https://ai.google.dev/docs)
- [OpenRouter Documentation](https://openrouter.ai/docs)
- [Presek AI Engine](core/ai_engine.py)
- [Presek LLM Router](core/llm_router.py)
