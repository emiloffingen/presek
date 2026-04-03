/**
 * Presek 5.1 — Living Portal Engine
 * Cleanup & Horizontal Dashboard Integration
 */

const UI = {

    /* ── Helpers ─────────────────────────────────────────── */

    _esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    },

    _relativeTime(dateStr) {
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return '';
            const now = new Date();
            const diff = (now - d) / 1000;
            if (diff < 60) return 'сега';
            if (diff < 3600) return `${Math.floor(diff / 60)}м`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}ч`;
            return d.toLocaleDateString('mk-MK', { day: 'numeric', month: 'short' });
        } catch (e) { return ''; }
    },

    /* ── Core Rendering ──────────────────────────────────── */

    state: {
        trends: []
    },

    renderPage(clusters, append = false, isPersonalized = false, isSearch = false) {
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
                this.updateDynamicTheme(clusters);
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
                if (isMobile && !append && idx === 3 && this.state.trends.length > 0) {
                    htmlBuffer += this._renderDiscoveryRibbon();
                }
                
                htmlBuffer += this._renderCluster(cluster, idx);
            } catch (e) { console.error("Cluster render error:", e); }
        });
        
        container.insertAdjacentHTML('beforeend', htmlBuffer);
    },

    _renderDiscoveryRibbon() {
        const items = this.state.trends.slice(0, 10).map(t => `
            <a href="#" class="ribbon-item" data-search="${encodeURIComponent(t.word)}">
                <span class="src-badge">HOT</span>
                <span class="ribbon-word">${this._esc(t.word)}</span>
            </a>
        `).join('');

        return `
            <div class="discovery-ribbon fade-in">
                <div class="ribbon-title">Трендови во моментов</div>
                <div class="ribbon-scroll">
                    ${items}
                </div>
            </div>`;
    },

    _renderCluster(cluster, idx) {
        const articles = cluster.articles || [];
        const main = articles[0];
        const count = articles.length;
        const isBookmarked = this.isBookmarked(cluster.cluster_id);
        
        // NYT Organic Grid Logic
        const isLead = app.state.page === 0 && idx === 0;
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
                    <img src="${thumbUrl}" alt="${this._esc(main.title)}" 
                         class="cluster-thumb loading" 
                         loading="${idx < 3 ? 'eager' : 'lazy'}"
                         onload="this.classList.remove('loading')"
                         onerror="this.classList.remove('loading'); this.classList.add('error'); this.src='/static/img/placeholder.svg';">
                </a>
            </div>` : '';

        const excerptHtml = (isLead || idx < 3) 
            ? `<p class="cluster-excerpt">${this._esc(main.description || '').substring(0, isLead ? 220 : 120)}...</p>` 
            : '';

        const variantClass = isLead ? 'lead-story' : (isThumbRight ? 'thumb-right' : '');

        return `
            <article class="news-cluster ${variantClass} fade-in">
                ${isThumbRight ? '' : imgHtml}
                <div class="cluster-main">
                    <a href="/cluster/${cluster.cluster_id}" class="cluster-headline">
                        ${this._esc(main.title)}
                    </a>
                    ${excerptHtml}
                    <div class="cluster-meta">
                        <span>${this._relativeTime(main.created_at)}</span>
                        <span>·</span>
                        <span>${count} извори</span>
                        ${bookmarkHtml}
                    </div>
                </div>
                ${isThumbRight ? imgHtml : ''}
            </article>`;
    },

    /* ── Bookmark Helpers ────────────────────────────────── */

    isBookmarked(clusterId) {
        try {
            const saved = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
            return saved.includes(clusterId);
        } catch (e) { return false; }
    },

    async shareCluster(title) {
        const shareData = {
            title: title || 'Пресек',
            text: title,
            url: window.location.href
        };

        try {
            if (navigator.share) {
                await navigator.share(shareData);
            } else {
                await navigator.clipboard.writeText(window.location.href);
                alert('Линкот е ископиран во таблата.');
            }
        } catch (err) {
            console.error('Share error:', err);
        }
    },

    toggleBookmark(event, clusterId) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        try {
            let saved = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
            const idx = saved.indexOf(clusterId);
            const isAdding = idx === -1;

            if (isAdding) {
                saved.push(clusterId);
            } else {
                saved.splice(idx, 1);
            }
            
            localStorage.setItem('presek_saved_clusters', JSON.stringify(saved));

            // Update UI globally
            document.querySelectorAll(`[onclick*="'${clusterId}'"]`).forEach(btn => {
                if (btn.classList.contains('bookmark-btn')) {
                    btn.classList.toggle('active', isAdding);
                    const svg = btn.querySelector('svg');
                    if (svg) svg.setAttribute('fill', isAdding ? 'currentColor' : 'none');
                    btn.title = isAdding ? 'Отстрани од зачувани' : 'Зачувај за подоцна';
                }
            });

            // If we are on the saved page, removing should trigger a refresh
            if (!isAdding && location.pathname === '/saved') {
                app.fetchNews();
            }

        } catch (e) { console.error("Bookmark toggle error:", e); }
    },

    _renderSkeletons(count = 3) {
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
    },

    /* ── Intelligence & Widgets ─────────────────────────── */

    updateDynamicTheme(clusters) {
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
    },

    renderPulse(entities) {
        const terminal = document.getElementById('entityPulse');
        if (!terminal || !entities || !Array.isArray(entities)) return;

        // Duplicate entities for seamless scroll effect
        const items = [...entities, ...entities]; 

        terminal.innerHTML = items.map(e => `
            <span class="ticker-item" data-search="${encodeURIComponent(e.word || e.name || e.source)}">
                #${this._esc(e.word || e.name || e.source)} <span class="val">${e.count || e.n || ''}</span>
            </span>
        `).join('');
        terminal.querySelectorAll('.ticker-item[data-search]').forEach(el => {
            el.addEventListener('click', () => app.setSearch(decodeURIComponent(el.dataset.search)));
        });
    },

    renderTrendingSidebar(trends) {
        this.state.trends = trends || []; // Store for Discovery Ribbon
        this._populateSearchSuggestions(trends); // Populate search overlay suggestions
        const sidebar = document.getElementById('sidebarTrending');
        if (!sidebar) return;
        
        sidebar.innerHTML = (trends || []).slice(0, 8).map(t => `
            <a href="#" class="related-link" style="padding: 8px 0; border-bottom: 1px solid var(--border);" data-search="${encodeURIComponent(t.word)}">
                <span class="src-badge">HOT</span>
                <span>${this._esc(t.word)}</span>
            </a>
        `).join('');
        
        // Delegate to handle both sidebar and ribbon clicks if needed
        document.querySelectorAll('[data-search]').forEach(el => {
            if (!el.dataset.searchBound) {
                el.addEventListener('click', (e) => { 
                    e.preventDefault(); 
                    app.setSearch(decodeURIComponent(el.dataset.search)); 
                    this.toggleDrawer(false); // Close drawer if open
                    const searchOverlay = document.getElementById('searchOverlay');
                    if (searchOverlay) searchOverlay.classList.remove('active');
                });
                el.dataset.searchBound = "true";
            }
        });
    },

    _populateSearchSuggestions(trends) {
        const container = document.getElementById('searchTrending');
        if (!container || !trends) return;

        container.innerHTML = trends.slice(0, 8).map(t => `
            <div class="suggestion-item" data-search="${encodeURIComponent(t.word)}">
                ${this._esc(t.word)}
            </div>
        `).join('');

        container.querySelectorAll('.suggestion-item').forEach(el => {
            el.addEventListener('click', () => {
                const query = decodeURIComponent(el.dataset.search);
                this._saveSearchToHistory(query);
                app.setSearch(query);
                const searchOverlay = document.getElementById('searchOverlay');
                if (searchOverlay) searchOverlay.classList.remove('active');
            });
        });
    },

    _saveSearchToHistory(query) {
        if (!query) return;
        try {
            let history = JSON.parse(localStorage.getItem('presek_search_history') || '[]');
            history = history.filter(h => h.toLowerCase() !== query.toLowerCase());
            history.unshift(query);
            history = history.slice(0, 5);
            localStorage.setItem('presek_search_history', JSON.stringify(history));
            this._renderSearchHistory();
        } catch (e) {}
    },

    _renderSearchHistory() {
        const container = document.getElementById('searchHistory');
        const section = document.getElementById('searchHistorySection');
        if (!container || !section) return;

        try {
            const history = JSON.parse(localStorage.getItem('presek_search_history') || '[]');
            if (history.length === 0) {
                section.style.display = 'none';
                return;
            }

            section.style.display = 'block';
            container.innerHTML = history.map(h => `
                <div class="suggestion-item history-item" data-search="${encodeURIComponent(h)}">
                    <span style="opacity: 0.5; margin-right: 6px;">⏳</span> ${this._esc(h)}
                </div>
            `).join('');

            container.querySelectorAll('.history-item').forEach(el => {
                el.addEventListener('click', () => {
                    const query = decodeURIComponent(el.dataset.search);
                    app.setSearch(query);
                    const searchOverlay = document.getElementById('searchOverlay');
                    if (searchOverlay) searchOverlay.classList.remove('active');
                });
            });
        } catch (e) {
            section.style.display = 'none';
        }
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    },

    init() {
        try { this._renderSearchHistory(); } catch(e) {}
        try { this._initBackToTop(); } catch(e) { console.error("BackToTop init error", e); }
        try { this._initMobileDrawer(); } catch(e) { console.error("MobileDrawer init error", e); }
        try { this._initSearchOverlay(); } catch(e) { console.error("SearchOverlay init error", e); }
        try { this._initReadingToolkit(); } catch(e) { console.error("ReadingToolkit init error", e); }
        try { this._initProgressBar(); } catch(e) { console.error("ProgressBar init error", e); }
        try { this._initPrivacyBanner(); } catch(e) { console.error("PrivacyBanner init error", e); }
        try { this._initStickyHeader(); } catch(e) { console.error("StickyHeader init error", e); }
    },

    _initStickyHeader() {
        const header = document.querySelector('.site-header');
        if (!header) return;

        let lastScroll = 0;
        window.addEventListener('scroll', () => {
            const currentScroll = window.pageYOffset;
            if (currentScroll <= 0) {
                header.classList.remove('hidden');
                return;
            }
            if (currentScroll > lastScroll && !header.classList.contains('hidden') && currentScroll > 200) {
                // Scroll Down
                header.classList.add('hidden');
            } else if (currentScroll < lastScroll && header.classList.contains('hidden')) {
                // Scroll Up
                header.classList.remove('hidden');
            }
            lastScroll = currentScroll;
        }, { passive: true });
    },

    _initReadingToolkit() {
        const btnInc = document.getElementById('tkInc');
        const btnDec = document.getElementById('tkDec');
        const root = document.documentElement;

        // Load saved size or default
        let currentSize = 1.15;
        try {
            currentSize = parseFloat(localStorage.getItem('presek_reading_size')) || 1.15;
        } catch (e) {}
        root.style.setProperty('--article-text-size', `${currentSize}rem`);

        if (btnInc) {
            btnInc.addEventListener('click', () => {
                if (currentSize < 1.6) {
                    currentSize += 0.1;
                    update();
                }
            });
        }
        
        if (btnDec) {
            btnDec.addEventListener('click', () => {
                if (currentSize > 0.9) {
                    currentSize -= 0.1;
                    update();
                }
            });
        }

        function update() {
            root.style.setProperty('--article-text-size', `${currentSize}rem`);
            try {
                localStorage.setItem('presek_reading_size', currentSize);
            } catch (e) {}
        }
    },

    _initProgressBar() {
        const bar = document.getElementById('readingProgress');
        if (!bar) return;

        window.addEventListener('scroll', () => {
            const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
            const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const scrolled = (winScroll / height) * 100;
            bar.style.width = scrolled + "%";
        }, { passive: true });
    },

    _initPrivacyBanner() {
        const banner = document.getElementById('privacyBanner');
        const accept = document.getElementById('privacyAccept');
        const reject = document.getElementById('privacyReject');

        let consent = null;
        try {
            consent = localStorage.getItem('presek_cookie_consent');
        } catch (e) {}

        if (!consent) {
            setTimeout(() => {
                if (banner) banner.classList.add('active');
            }, 2000);
        }

        if (accept) {
            accept.addEventListener('click', () => {
                try { localStorage.setItem('presek_cookie_consent', 'accepted'); } catch(e) {}
                if (banner) banner.classList.remove('active');
            });
        }
        
        if (reject) {
            reject.addEventListener('click', () => {
                try { localStorage.setItem('presek_cookie_consent', 'rejected'); } catch(e) {}
                if (banner) banner.classList.remove('active');
            });
        }
    },

    _initSearchOverlay() {
        const overlay = document.getElementById('searchOverlay');
        const close = document.getElementById('searchClose');
        const clear = document.getElementById('searchClear');
        const input = document.getElementById('searchInput');

        if (overlay && close) {
            close.addEventListener('click', () => overlay.classList.remove('active'));
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) overlay.classList.remove('active');
            });
        }

        if (input && clear) {
            input.addEventListener('input', () => {
                clear.style.display = input.value ? 'flex' : 'none';
            });
            clear.addEventListener('click', () => {
                input.value = '';
                clear.style.display = 'none';
                input.focus();
            });
        }
    },

    toggleDrawer(show) {
        const drawer = document.getElementById('mobileDrawer');
        const overlay = document.getElementById('drawerOverlay');
        const trigger = document.getElementById('menuTrigger');
        if (!drawer || !overlay) return;
        
        const isOpening = show !== false;
        drawer.classList.toggle('active', isOpening);
        overlay.classList.toggle('active', isOpening);
        document.body.style.overflow = isOpening ? 'hidden' : '';

        if (trigger) {
            trigger.setAttribute('aria-expanded', isOpening);
        }

        if (isOpening) {
            // Focus the close button or first link in drawer
            setTimeout(() => {
                const closeBtn = document.getElementById('drawerClose');
                if (closeBtn) closeBtn.focus();
            }, 100);
        } else {
            // Restore focus to trigger
            if (trigger) trigger.focus();
        }
    },

    _initMobileDrawer() {
        const trigger = document.getElementById('menuTrigger');
        const close = document.getElementById('drawerClose');
        const overlay = document.getElementById('drawerOverlay');

        if (trigger) trigger.addEventListener('click', () => this.toggleDrawer(true));
        if (close) close.addEventListener('click', () => this.toggleDrawer(false));
        if (overlay) overlay.addEventListener('click', () => this.toggleDrawer(false));
    },

    _initBackToTop() {
        const btn = document.getElementById('backToTop');
        if (!btn) return;
        window.addEventListener('scroll', () => {
            if (window.scrollY > 500) {
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';
                btn.style.transform = 'translateY(0)';
            } else {
                btn.style.opacity = '0';
                btn.style.pointerEvents = 'none';
                btn.style.transform = 'translateY(10px)';
            }
        }, { passive: true });
        btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    }

};

setInterval(() => UI.updateClock(), 1000);
UI.updateClock();
UI.init();

window.UI = UI;

/* ── Follow helpers (used by source.html) ───────────────── */

function isFollowing(type, value) {
    try {
        const data = JSON.parse(localStorage.getItem(`presek_follow_${type}`) || '[]');
        return data.includes(value);
    } catch(e) { return false; }
}

function toggleFollow(type, value) {
    try {
        const key = `presek_follow_${type}`;
        let data = JSON.parse(localStorage.getItem(key) || '[]');
        const idx = data.indexOf(value);
        if (idx === -1) data.push(value);
        else data.splice(idx, 1);
        localStorage.setItem(key, JSON.stringify(data));
    } catch(e) {}
}
