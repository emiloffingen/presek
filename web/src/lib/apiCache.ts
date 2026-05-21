import { apiBaseUrl } from './apiBase';

const API_URL = apiBaseUrl();

async function fetchJson(url: string) {
    const response = await fetch(url);
    if (!response.ok) {
        const err: any = new Error(`Request failed: ${response.status} ${url}`);
        err.status = response.status;
        throw err;
    }
    return response.json();
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
