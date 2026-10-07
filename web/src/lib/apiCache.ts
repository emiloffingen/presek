import { apiBaseUrl } from './apiBase';

const API_URL = apiBaseUrl();

export async function fetchJson(url: string, retries = 2, init?: RequestInit) {
    const externalSignal = init?.signal;
    for (let attempt = 0; attempt <= retries; attempt++) {
        if (externalSignal?.aborted) {
            throw new DOMException('Aborted', 'AbortError');
        }
        let timedOut = false;
        try {
            const controller = new AbortController();
            const timer = setTimeout(() => {
                timedOut = true;
                controller.abort();
            }, 30000);
            const onExternalAbort = () => controller.abort();
            externalSignal?.addEventListener('abort', onExternalAbort, { once: true });
            let response: Response;
            try {
                response = await fetch(url, { ...init, signal: controller.signal });
            } finally {
                clearTimeout(timer);
                externalSignal?.removeEventListener('abort', onExternalAbort);
            }
            if (!response.ok) {
                const err: any = new Error(`Request failed: ${response.status} ${url}`);
                err.status = response.status;
                throw err;
            }
            return response.json();
        } catch (err: any) {
            // Caller-cancelled requests must never be retried, and neither should
            // our own timeout (otherwise a hung endpoint is attempted 3x = ~90s).
            if (externalSignal?.aborted) throw err;
            const retryable = err.cause?.code === 'UND_ERR_SOCKET' || (err.name === 'AbortError' && !timedOut);
            if (attempt < retries && retryable) {
                await new Promise(r => setTimeout(r, 100 * (attempt + 1)));
                continue;
            }
            throw err;
        }
    }
    throw new Error(`fetchJson exhausted retries: ${url}`);
}

// Module-level cache maps that persist across requests.
// Bounded LRU: distinct search/filter URLs are high-cardinality and would
// otherwise accumulate promises for the process lifetime on long-lived workers.
const apiCache = new Map<string, Promise<any>>();
const apiCacheExpiry = new Map<string, number>();
const DEFAULT_TTL_MS = 60 * 1000; // 60 seconds
const API_CACHE_MAX_ENTRIES = 500;
// Query-param URLs (search text, filters) are effectively unique per request:
// cache them only briefly for stampede protection, never for the full TTL.
const HIGH_CARDINALITY_TTL_MS = 5 * 1000; // 5 seconds

function apiCacheEvictIfNeeded() {
    if (apiCache.size < API_CACHE_MAX_ENTRIES) return;
    // Maps iterate in insertion order: refresh recency by re-inserting below,
    // so the head is always the least-recently-used entry.
    const oldest = apiCache.keys().next();
    if (!oldest.done) {
        apiCache.delete(oldest.value);
        apiCacheExpiry.delete(oldest.value);
    }
}

/**
 * Fetches JSON from the API, caching the promise to resolve concurrent requests
 * and prevent backend stampedes.
 */
export function fetchJsonCached(url: string, ttlMs = DEFAULT_TTL_MS): Promise<any> {
    const now = Date.now();
    const highCardinality = url.includes('?');
    const effectiveTtl = highCardinality ? Math.min(ttlMs, HIGH_CARDINALITY_TTL_MS) : ttlMs;
    const expiresAt = apiCacheExpiry.get(url);
    let promise = apiCache.get(url);

    // If cache misses, or is expired, trigger a new request promise
    if (!promise || !expiresAt || now > expiresAt) {
        promise = fetchJson(url).catch((err) => {
            // Clean up on failure so subsequent requests can try again
            apiCache.delete(url);
            apiCacheExpiry.delete(url);
            throw err;
        });
        apiCache.delete(url); // re-insert for LRU recency
        apiCacheEvictIfNeeded();
        apiCache.set(url, promise);
        apiCacheExpiry.set(url, now + effectiveTtl);
    } else {
        // Cache hit: refresh LRU recency.
        apiCache.delete(url);
        apiCache.set(url, promise);
    }
    return promise;
}
