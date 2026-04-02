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
        const container = document.getElementById('pageWrap');
        if (!container) return;

        if (!append) {
            // Smoothly clear container without jump
            container.innerHTML = '';
            
            if (isPersonalized && !isSearch) {
                container.innerHTML = `
                    <div class="personalization-notice fade-in">
                        <span class="p-icon">✨</span> ПЕРСОНАЛИЗИРАН ИЗБОР ЗА ВАС
                    </div>`;
            }

            if (isSearch) {
                container.innerHTML = `
                    <div class="search-notice fade-in" style="margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">
                        <h2 style="font-size: 1.2rem; font-family: var(--font-heading);">Резултати од пребарувањето</h2>
                    </div>`;
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

        const eyebrow = `
            <div class="card-eyebrow">
                <span class="card-source">${this._esc(main.source)}</span>
                <span class="card-dot">·</span>
                <span class="card-time">${this._relativeTime(main.created_at)}</span>
                ${main.category ? `<span class="card-category">${this._esc(main.category)}</span>` : ''}
                ${cluster.is_breaking ? `<span class="card-breaking">🚨 БРЕЈКИНГ</span>` : ''}
            </div>`;

        const countBadge = `
            <span class="card-eyebrow">
                <span class="card-count">${count} извори</span>
                ${cluster.has_balanced ? `<span class="card-balanced">⚖️ Балансирано</span>` : ''}
            </span>`;

        // Hero card (every 6th: 0, 6, 12, ...)
        if (idx % 6 === 0) {
            const imgHtml = thumbUrl ? `
                <div class="card-hero__image">
                    <a href="/cluster/${cluster.cluster_id}" style="display:block;width:100%;height:100%;">
                        <img src="${thumbUrl}" alt="${this._esc(main.title)}" loading="eager">
                    </a>
                </div>` : '';
            return `
                <article class="card-hero span-12 row-2 fade-in">
                    ${imgHtml}
                    <div class="card-hero__body">
                        ${eyebrow}
                        <a href="/cluster/${cluster.cluster_id}" class="card-hero__headline">${this._esc(main.title)}</a>
                        <div class="card-hero__foot">
                            <a href="/cluster/${cluster.cluster_id}" class="card-hero__cta">ВИДИ РЕЗИМЕ</a>
                            ${countBadge}
                        </div>
                    </div>
                </article>`;
        }

        // Row card (every 4th in the pattern: 3, 9, 15, ...)
        if (idx % 6 === 3) {
            const imgHtml = thumbUrl ? `
                <div class="card-row__image">
                    <a href="/cluster/${cluster.cluster_id}" style="display:block;width:100%;height:100%;">
                        <img src="${thumbUrl}" alt="${this._esc(main.title)}" loading="lazy">
                    </a>
                </div>` : '';
            return `
                <article class="card-row span-12 fade-in">
                    <div class="card-row__body">
                        ${eyebrow}
                        <a href="/cluster/${cluster.cluster_id}" class="card-row__headline">${this._esc(main.title)}</a>
                        <div class="card-row__foot">${countBadge}</div>
                    </div>
                    ${imgHtml}
                </article>`;
        }

        // Mid card (idx%6 === 1,2,4,5)
        const imgHtml = thumbUrl ? `
            <div class="card-mid__image">
                <a href="/cluster/${cluster.cluster_id}" style="display:block;width:100%;height:100%;">
                    <img src="${thumbUrl}" alt="${this._esc(main.title)}" loading="lazy">
                </a>
            </div>` : `<div class="card-mid__image-placeholder">📰</div>`;
        return `
            <article class="card-mid span-6 fade-in">
                ${imgHtml}
                <div class="card-mid__body">
                    ${eyebrow}
                    <a href="/cluster/${cluster.cluster_id}" class="card-mid__headline">${this._esc(main.title)}</a>
                    <div class="card-mid__foot">${countBadge}</div>
                </div>
            </article>`;
    },

    /* ── Intelligence & Widgets ─────────────────────────── */

    updateDynamicTheme(clusters) {
        const counts = {};
        clusters.forEach(c => {
            const cat = c.articles[0]?.category || 'Сите';
            counts[cat] = (counts[cat] || 0) + 1;
        });

        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        const dominant = sorted[0] ? sorted[0][0] : 'Сите';
        
        const hues = { 'Македонија': 355, 'Политика': 355, 'Економија': 210, 'Свет': 200, 'Балкан': 30, 'Спорт': 145, 'Технологија': 280, 'Забава': 320 };
        const targetHue = hues[dominant] || 355;
        document.documentElement.style.setProperty('--p-h', targetHue);
    },

    renderPulse(entities) {
        const terminal = document.getElementById('entityPulse');
        if (!terminal) return;

        // Duplicate entities for seamless scroll effect
        const items = [...entities, ...entities]; 

        terminal.innerHTML = items.map(e => `
            <span class="ticker-item" data-search="${encodeURIComponent(e.word || e.name)}">
                #${this._esc(e.word || e.name)} <span class="val">${e.count || e.n || ''}</span>
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
            el.onclick = () => {
                app.setSearch(decodeURIComponent(el.dataset.search));
                const searchOverlay = document.getElementById('searchOverlay');
                if (searchOverlay) searchOverlay.classList.remove('active');
            };
        });
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    },

    init() {
        this._initBackToTop();
        this._initMobileDrawer();
        this._initSearchOverlay();
        this._initReadingToolkit();
        this._initProgressBar();
        this._initPrivacyBanner();
    },

    _initReadingToolkit() {
        const btnInc = document.getElementById('tkInc');
        const btnDec = document.getElementById('tkDec');
        const root = document.documentElement;

        // Load saved size or default
        let currentSize = parseFloat(localStorage.getItem('presek_reading_size')) || 1.15;
        root.style.setProperty('--article-text-size', `${currentSize}rem`);

        if (btnInc && btnDec) {
            btnInc.onclick = () => {
                if (currentSize < 1.6) {
                    currentSize += 0.1;
                    update();
                }
            };
            btnDec.onclick = () => {
                if (currentSize > 0.9) {
                    currentSize -= 0.1;
                    update();
                }
            };
        }

        function update() {
            root.style.setProperty('--article-text-size', `${currentSize}rem`);
            localStorage.setItem('presek_reading_size', currentSize);
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

        if (!localStorage.getItem('presek_cookie_consent')) {
            setTimeout(() => {
                if (banner) banner.classList.add('active');
            }, 2000);
        }

        if (accept) accept.onclick = () => {
            localStorage.setItem('presek_cookie_consent', 'accepted');
            if (banner) banner.classList.remove('active');
        };
        if (reject) reject.onclick = () => {
            localStorage.setItem('presek_cookie_consent', 'rejected');
            if (banner) banner.classList.remove('active');
        };
    },

    _initSearchOverlay() {
        const overlay = document.getElementById('searchOverlay');
        const close = document.getElementById('searchClose');
        if (overlay && close) {
            close.onclick = () => overlay.classList.remove('active');
            // Close on backdrop click
            overlay.onclick = (e) => {
                if (e.target === overlay) overlay.classList.remove('active');
            };
        }
    },

    toggleDrawer(show) {
        const drawer = document.getElementById('mobileDrawer');
        const overlay = document.getElementById('drawerOverlay');
        if (!drawer || !overlay) return;
        
        drawer.classList.toggle('active', show !== false);
        overlay.classList.toggle('active', show !== false);
        document.body.style.overflow = (show !== false) ? 'hidden' : '';
    },

    _initMobileDrawer() {
        const trigger = document.getElementById('menuTrigger');
        const close = document.getElementById('drawerClose');
        const overlay = document.getElementById('drawerOverlay');

        if (trigger) trigger.onclick = () => this.toggleDrawer(true);
        if (close) close.onclick = () => this.toggleDrawer(false);
        if (overlay) overlay.onclick = () => this.toggleDrawer(false);
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
        btn.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
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
