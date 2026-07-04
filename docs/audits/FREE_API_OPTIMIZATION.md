# Free API Keys Optimization Guide

## Overview

Since all AI API keys are currently free, we can optimize the Smart Model Router to prioritize quality over cost. This guide explains how to configure and use the free API mode.

## Configuration

### Enable Free API Mode

Add this to your `.env` file:

```env
# Enable free API optimization mode
FREE_API_KEYS_ENABLED=true
```

### Router Behavior Comparison

#### Normal Mode (Cost-Optimized)
```
Low complexity (1-2 articles):     local (Gemma 4 E2B)
Medium complexity (3-4 articles):  mistral_small
High complexity (5+ articles):    mistral_large
```

#### Free API Mode (Quality-Optimized)
```
Low complexity (1-2 articles):     mistral_small  ← Upgraded!
Medium complexity (3-4 articles):  mistral_small
High complexity (5+ articles):    mistral_large
```

## Benefits of Free API Mode

### 1. **Consistent Quality**
- All content gets Mistral-level quality
- No quality variation between simple and complex stories
- Better handling of nuance and context

### 2. **Reduced Local Load**
- Local Gemma model used less frequently
- Lower CPU/memory usage on your servers
- Better system resource allocation

### 3. **Future-Proof**
- Easy to switch back when APIs become paid
- Performance data collected for all providers
- Quality metrics available for comparison

### 4. **Better User Experience**
- More consistent synthesis quality
- Better handling of edge cases
- Improved language understanding

## Monitoring & Metrics

The enhanced router tracks performance for all providers:

```python
from core.llm_router import SmartModelRouter

# Get current performance stats
for provider, stats in SmartModelRouter._provider_performance.items():
    perf = SmartModelRouter._get_provider_performance(provider)
    print(f"{provider}: Success={perf['success_rate']:.1%}, Latency={perf['avg_latency']:.1f}s")

# Get dynamic fallback order (performance-based)
dynamic_order = SmartModelRouter.get_dynamic_fallback_order()
print(f"Optimal order: {dynamic_order}")
```

## Quality Tracking

The system automatically tracks synthesis quality by provider:

```python
# View quality metrics
for provider, samples in SmartModelRouter._provider_quality.items():
    avg_quality = sum(s['score'] for s in samples) / len(samples)
    print(f"{provider}: {len(samples)} samples, avg quality={avg_quality:.2f}")
```

## Recommended Usage

### When to Use Free API Mode
- ✅ During free trial periods
- ✅ When API credits are abundant
- ✅ For high-quality content production
- ✅ During low-traffic periods

### When to Use Normal Mode
- ❌ When API costs are a concern
- ❌ During high-traffic spikes
- ❌ When local model is sufficient
- ❌ For testing/development

## Performance Considerations

### Response Time Comparison
```
Local Gemma:       ~0.5s
Mistral Small:     ~2.0s
Mistral Large:     ~3.5s
NVIDIA:            ~35s (much slower)
```

### Throughput Impact
- Free API mode increases average response time from ~1s to ~2s
- Overall throughput may decrease by 30-50%
- Consider increasing worker concurrency if needed

## Fallback Behavior

Even in free API mode, the system maintains robust fallbacks:

1. **Primary**: Mistral Small/Large (as appropriate)
2. **Secondary**: Other remote providers
3. **Final**: Local Gemma (always available)

The dynamic fallback order adjusts based on real-time performance.

## Disabling Free API Mode

Simply remove or set to false:

```env
FREE_API_KEYS_ENABLED=false
```

Or remove the line entirely to revert to cost-optimized routing.

## Monitoring Recommendations

1. **Track API Usage**: Monitor Mistral/NVIDIA API call volumes
2. **Watch Latency**: Ensure response times remain acceptable
3. **Compare Quality**: Review synthesis quality metrics
4. **Check Costs**: Verify no unexpected charges appear

## Migration Checklist

- [ ] Add `FREE_API_KEYS_ENABLED=true` to `.env`
- [ ] Monitor system for 24-48 hours
- [ ] Compare quality metrics before/after
- [ ] Adjust worker concurrency if needed
- [ ] Update monitoring dashboards
- [ ] Document the change in your operations log

---

*Last updated: June 2026 • Presek AI Optimization Guide*