import { appState, uiState } from './state.js';
import { _esc, _relativeTime, _saveSearchToHistory } from './utils.js';

export function renderPage(clusters, append = false, isPersonalized = false, isSearch = false) {
    const container = document.getElementById('newsFeed');
    if (!container) return;

    if (!append) {
        // Smoothly clear container without jump
        container.innerHTML = '';
        
        if (isPersonalized && !isSearch) {
            container.insertAdjacentHTML('beforebegin', `
                <div class="personalization-notice fade-in">
                    <span class="p-icon">✨</span> ПЕРСОНАЛИЗИРАН ИЗБОР ЗА ВАС
                </div>`);
        }

        if (isSearch) {
            container.insertAdjacentHTML('beforebegin', `
                <div class="search-notice fade-in" style="margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">
                    <h2 style="font-size: 1.2rem; font-family: var(--font-heading);">Резултати од пребарувањето</h2>
                </div>`);
        }

        if (clusters && clusters.length > 0 && !isSearch) {
            updateDynamicTheme(clusters);
        }
    }

    if (!clusters || !Array.isArray(clusters) || clusters.length === 0) {
        if (!append) {
            container.innerHTML = `
                <div class="error-state fade-in" style="padding: 4rem; text-align: center; color: var(--text-muted);">
                    <p>Нема пронајдено вести за избраните критериуми.</p>
                    <button class="cat-btn" style="margin-top: 1rem; background: var(--bg-elevated);" onclick="location.reload()">Освежи</button>
                </div>`;
        }
        return;
    }

    const isMobile = window.innerWidth <= 780;
    let htmlBuffer = '';
    
    clusters.forEach((cluster, idx) => {
        try {
            if (!cluster || !cluster.articles || !cluster.articles.length) return;
            
            // Inject Discovery Ribbon on mobile between 3rd and 4th item (idx 2 and 3)
            if (isMobile && !append && idx === 3 && uiState.trends.length > 0) {
                htmlBuffer += _renderDiscoveryRibbon();
            }
            
            htmlBuffer += _renderCluster(cluster, idx);
        } catch (e) { console.error("Cluster render error:", e); }
    });
    
    container.insertAdjacentHTML('beforeend', htmlBuffer);
}

export function _renderDiscoveryRibbon() {
    const items = uiState.trends.slice(0, 10).map(t => `
        <a href="#" class="ribbon-item" data-search="${encodeURIComponent(t.word)}">
            <span class="src-badge">HOT</span>
            <span class="ribbon-word">${_esc(t.word)}</span>
        </a>
    `).join('');

    return `
        <div class="discovery-ribbon fade-in">
            <div class="ribbon-title">Трендови во моментов</div>
            <div class="ribbon-scroll">
                ${items}
            </div>
        </div>`;
}

export function _renderCluster(cluster, idx) {
    const articles = cluster.articles || [];
    const main = articles[0];
    const count = articles.length;
    const isBookmarked = window.UI.isBookmarked(cluster.cluster_id);
    
    // NYT Organic Grid Logic
    const isLead = appState.page === 0 && idx === 0;
    const isThumbRight = !isLead && (idx % 5 === 0); // Break monotony every 5th item

    let thumbUrl = cluster.representative_image;
    if (thumbUrl && !thumbUrl.startsWith('/')) thumbUrl = `/proxy?url=${encodeURIComponent(thumbUrl)}`;
    if (!thumbUrl) {
        for (const a of articles) {
            if (a && a.image_url) {
                thumbUrl = a.image_url.startsWith('/') ? a.image_url : `/proxy?url=${encodeURIComponent(a.image_url)}`;
                break;
            }
        }
    }

    const bookmarkHtml = `
        <button class="bookmark-btn ${isBookmarked ? 'active' : ''}" 
                onclick="UI.toggleBookmark(event, '${cluster.cluster_id}')" 
                title="${isBookmarked ? 'Отстрани од зачувани' : 'Зачувај за подоцна'}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="${isBookmarked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2.5">
                <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
            </svg>
        </button>`;

    const imgHtml = thumbUrl ? `
        <div class="cluster-thumb-wrap">
            <a href="/cluster/${cluster.cluster_id}" style="display:block;width:100%;height:100%;">
                <img src="${thumbUrl}&w=20" alt="${_esc(main.title)}" 
                     class="cluster-thumb loading" 
                     loading="${idx < 3 ? 'eager' : 'lazy'}"
                     onload="const fullImg = new Image(); fullImg.src='${thumbUrl}'; fullImg.onload = () => { this.src = fullImg.src; this.classList.remove('loading'); };"
                     onerror="this.classList.remove('loading'); this.classList.add('error'); this.src='/static/img/placeholder.svg';">
            </a>
        </div>` : '';

    const excerptHtml = (isLead || idx < 3) 
        ? `<p class="cluster-excerpt">${_esc(main.description || '').substring(0, isLead ? 220 : 120)}...</p>` 
        : '';

    const variantClass = isLead ? 'lead-story' : (isThumbRight ? 'thumb-right' : '');

    const readingTimeHtml = cluster.reading_time ? `<span>·</span><span>${cluster.reading_time}м читање</span>` : '';

    return `
        <article class="news-cluster ${variantClass} fade-in">
            ${isThumbRight ? '' : imgHtml}
            <div class="cluster-main">
                <a href="/cluster/${cluster.cluster_id}" class="cluster-headline">
                    ${_esc(main.title)}
                </a>
                ${excerptHtml}
                <div class="cluster-meta">
                    <span>${_relativeTime(main.created_at)}</span>
                    <span>·</span>
                    <span>${count} извори</span>
                    ${readingTimeHtml}
                    ${bookmarkHtml}
                </div>
            </div>
            ${isThumbRight ? imgHtml : ''}
        </article>`;
}

export function _renderSkeletons(count = 3) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `
            <div class="news-cluster span-3 skeleton-card" style="min-height: 300px;">
                <div class="skeleton-box" style="width: 100%; aspect-ratio: 16/9; margin-bottom: 1rem;"></div>
                <div class="skeleton-box" style="width: 40%; height: 0.7rem; margin-bottom: 0.8rem;"></div>
                <div class="skeleton-box" style="width: 90%; height: 1.2rem; margin-bottom: 0.5rem;"></div>
                <div class="skeleton-box" style="width: 70%; height: 1.2rem; margin-bottom: 1rem;"></div>
                <div style="display:flex; gap: 8px;">
                    <div class="skeleton-box" style="width: 60px; height: 1.2rem; border-radius: 4px;"></div>
                    <div class="skeleton-box" style="width: 40px; height: 1.2rem; border-radius: 4px;"></div>
                </div>
            </div>`;
    }
    return html;
}

export function updateDynamicTheme(clusters) {
    const counts = {};
    clusters.forEach(c => {
        if (c.articles && c.articles[0]) {
            const cat = c.articles[0].category || 'Сите';
            counts[cat] = (counts[cat] || 0) + 1;
        }
    });

    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const dominant = sorted[0] ? sorted[0][0] : 'Сите';
    
    const hues = { 'Македонија': 355, 'Политика': 355, 'Економија': 210, 'Свет': 200, 'Балкан': 30, 'Спорт': 145, 'Технологија': 280, 'Забава': 320 };
    const targetHue = hues[dominant] || 355;
    document.documentElement.style.setProperty('--p-h', targetHue);
}

export function renderPulse(entities) {
    const terminal = document.getElementById('entityPulse');
    if (!terminal) return;

    if (!entities || !Array.isArray(entities) || entities.length === 0) {
        terminal.innerHTML = `
            <span class="skeleton-box" style="width: 80px; height: 12px; display: inline-block; margin-right: 20px; border-radius: 2px;"></span>
            <span class="skeleton-box" style="width: 120px; height: 12px; display: inline-block; margin-right: 20px; border-radius: 2px;"></span>
            <span class="skeleton-box" style="width: 100px; height: 12px; display: inline-block; margin-right: 20px; border-radius: 2px;"></span>
        `;
        return;
    }

    // Duplicate entities for seamless scroll effect
    const items = [...entities, ...entities]; 

    terminal.innerHTML = items.map(e => `
        <span class="ticker-item" data-search="${encodeURIComponent(e.word || e.name || e.source)}">
            #${_esc(e.word || e.name || e.source)} <span class="val">${e.count || e.n || ''}</span>
        </span>
    `).join('');
    terminal.querySelectorAll('.ticker-item[data-search]').forEach(el => {
        el.addEventListener('click', () => window.app.setSearch(decodeURIComponent(el.dataset.search)));
    });
}

export function renderTrendingSidebar(trends) {
    uiState.trends = trends || []; // Store for Discovery Ribbon
    _populateSearchSuggestions(trends); // Populate search overlay suggestions
    const sidebar = document.getElementById('sidebarTrending');
    if (!sidebar) return;
    
    if (!trends || !Array.isArray(trends) || trends.length === 0) {
        sidebar.innerHTML = `
            <div style="padding: 10px 0;">
                <div class="skeleton-box" style="width: 90%; height: 1rem; margin-bottom: 12px;"></div>
                <div class="skeleton-box" style="width: 80%; height: 1rem; margin-bottom: 12px;"></div>
                <div class="skeleton-box" style="width: 85%; height: 1rem; margin-bottom: 12px;"></div>
                <div class="skeleton-box" style="width: 70%; height: 1rem;"></div>
            </div>`;
        return;
    }

    sidebar.innerHTML = (trends || []).slice(0, 8).map(t => `
        <a href="#" class="related-link" style="padding: 8px 0; border-bottom: 1px solid var(--border);" data-search="${encodeURIComponent(t.word)}">
            <span class="src-badge">HOT</span>
            <span>${_esc(t.word)}</span>
        </a>
    `).join('');
    
    // Delegate to handle both sidebar and ribbon clicks if needed
    document.querySelectorAll('[data-search]').forEach(el => {
        if (!el.dataset.searchBound) {
            el.addEventListener('click', (e) => { 
                e.preventDefault(); 
                window.app.setSearch(decodeURIComponent(el.dataset.search)); 
                window.UI.toggleDrawer(false); // Close drawer if open
                const searchOverlay = document.getElementById('searchOverlay');
                if (searchOverlay) searchOverlay.classList.remove('active');
            });
            el.dataset.searchBound = "true";
        }
    });
}

export function _populateSearchSuggestions(trends) {
    const container = document.getElementById('searchTrending');
    if (!container || !trends) return;

    container.innerHTML = trends.slice(0, 8).map(t => `
        <div class="suggestion-item" data-search="${encodeURIComponent(t.word)}">
            ${_esc(t.word)}
        </div>
    `).join('');

    container.querySelectorAll('.suggestion-item').forEach(el => {
        el.addEventListener('click', () => {
            const query = decodeURIComponent(el.dataset.search);
            _saveSearchToHistory(query);
            window.app.setSearch(query);
            const searchOverlay = document.getElementById('searchOverlay');
            if (searchOverlay) searchOverlay.classList.remove('active');
        });
    });
}
