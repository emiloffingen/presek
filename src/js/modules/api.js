import { appState } from './state.js';
import { showToast, _getTopInterests } from './utils.js';

export async function fetchNews(append = false) {
    if (appState.isFetching) return;
    appState.isFetching = true;

    const container = document.getElementById('pageWrap');
    const isSearch = !!appState.query;

    if (!append && container) {
        appState.page = 0;
        container.innerHTML = `<div class="loading-state" style="padding: 2rem; text-align: center; color: var(--text-muted);">${isSearch ? 'Пребарување...' : 'Вчитување вести...'}</div>`;
    }

    // PERCEPTION UPGRADE: Append skeletons immediately if infinite scrolling
    let skeletonBuffer = null;
    if (append && container && window.UI) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = window.UI._renderSkeletons(3);
        skeletonBuffer = Array.from(tempDiv.children);
        skeletonBuffer.forEach(s => container.appendChild(s));
    }

    // Handle Saved mode (offline/local)
    if (appState.isSaved) {
        try {
            if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());
            const savedIds = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
            if (savedIds.length === 0) {
                if (container) container.innerHTML = `<div class="error-state fade-in" style="padding: 4rem; text-align: center; color: var(--text-muted);"><p>Немате зачувано вести.</p></div>`;
                appState.isFetching = false;
                return;
            }
            
            // Fetch full cluster data for these IDs
            const res = await fetch(`/api/news?ids=${savedIds.join(',')}`);
            const data = await res.json();
            if (data && data.clusters) {
                if (window.UI) window.UI.renderPage(data.clusters, false, false, false);
            }
            appState.hasMore = false;
        } catch (e) { console.error(e); }
        appState.isFetching = false;
        return;
    }

    const params = new URLSearchParams({
        page: appState.page,
        page_size: appState.pageSize
    });

    if (appState.topic) params.set('topic', appState.topic);
    if (appState.query) params.set('q', appState.query);
    
    // Add local interests if browsing home page
    let isPersonalized = false;
    if (!appState.topic && !appState.query && !appState.isSaved) {
        const topCats = _getTopInterests('topic');
        if (topCats) {
            params.set('follow_topics', topCats);
            isPersonalized = true;
        }
        
        try {
            const followedSources = JSON.parse(localStorage.getItem('presek_follow_sources') || '[]');
            if (followedSources.length > 0) {
                params.set('follow_sources', followedSources.join(','));
                isPersonalized = true;
            }
        } catch (e) {}
    }

    try {
        const res = await fetch(`/api/news?${params}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Remove skeletons
        if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());

        if (data && data.status === 'success' && data.clusters) {
            if (window.UI) window.UI.renderPage(data.clusters, append, isPersonalized, isSearch);
            appState.hasMore = data.has_more;
        }
    } catch (e) {
        console.error('Fetch news error:', e);
        if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());
        if (!append) {
            if (container) container.innerHTML = `<div class="error-state fade-in" style="padding:4rem;text-align:center;color:var(--text-muted);"><p>Грешка при вчитување на вести.</p><button class="cat-btn" style="margin-top:1rem;background:var(--bg-elevated);" onclick="location.reload()">Обиди се повторно</button></div>`;
        }
    } finally {
        appState.isFetching = false;
    }
}

export async function fetchTrending() {
    try {
        const res = await fetch('/api/trending');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (window.UI) {
            window.UI.renderTrendingSidebar(data);
            window.UI.renderPulse(data);
        }
    } catch (e) { console.error('Trending fetch failed:', e); }
}

export function fetchWeather() {
    fetch('/api/weather')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
            if (!d) return;
            const wEl = document.getElementById('weatherVal');
            const aEl = document.getElementById('aqiVal');
            if (wEl && d.temp !== null) wEl.textContent = `${d.icon || ''} ${d.temp}°C`;
            if (aEl && d.aqi !== null) aEl.textContent = `AQI ${d.aqi}`;
        })
        .catch(() => {});
}

export function initLiveUpdates() {
    if (!window.EventSource) return;
    const source = new EventSource('/api/live');
    
    source.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'new_clusters' || data.type === 'ingestion_complete') {
                showToast(data.message || 'Нови вести се пристигнати');
            }
        } catch (err) {}
    };
    
    source.onerror = () => source.close();
}
