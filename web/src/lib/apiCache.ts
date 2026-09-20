import { apiBaseUrl } from './apiBase';

const API_URL = apiBaseUrl();

export async function fetchJson(url: string, retries = 2, init?: RequestInit) {
    const externalSignal = init?.signal;
    for (let attempt = 0; attempt <= retries; attempt++) {
        if (externalSignal?.aborted) {
            throw new DOMException('Aborted', 'AbortError');
        }
        try {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 30000);
            const onExternalAbort = () => controller.abort();
            externalSignal?.addEventListener('abort', onExternalAbort, { once: true });
            let response: Response;
            try {
                response = await fetch(url, { signal: controller.signal });
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
            // Caller-cancelled requests must never be retried.
            if (externalSignal?.aborted) throw err;
            if (attempt < retries && (err.cause?.code === 'UND_ERR_SOCKET' || err.name === 'AbortError')) {
                await new Promise(r => setTimeout(r, 100 * (attempt + 1)));
                continue;
            }
            throw err;
        }
    }
    throw new Error(`fetchJson exhausted retries: ${url}`);
}

// Module-level cache maps that persist across requests
const apiCache = new Map<string, Promise<any>>();
const apiCacheExpiry = new Map<string, number>();
const DEFAULT_TTL_MS = 60 * 1000; // 60 seconds

/**
 * Fetches JSON from the API, caching the promise to resolve concurrent requests
 * and prevent backend stampedes.
 */
export function fetchJsonCached(url: string, ttlMs = DEFAULT_TTL_MS): Promise<any> {
    const now = Date.now();
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
        apiCache.set(url, promise);
        apiCacheExpiry.set(url, now + ttlMs);
    }
    return promise;
}
