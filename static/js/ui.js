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

        let htmlBuffer = '';
        clusters.forEach((cluster, idx) => {
            try {
                if (!cluster || !cluster.articles || !cluster.articles.length) return;
                htmlBuffer += this._renderCluster(cluster, idx);
            } catch (e) { console.error("Cluster render error:", e); }
        });
        
        container.insertAdjacentHTML('beforeend', htmlBuffer);
    },

    _renderCluster(cluster, idx) {
        const articles = cluster.articles || [];
        const main = articles[0];
        const count = articles.length;
        
        let thumbUrl = cluster.representative_image;
        if (thumbUrl && !thumbUrl.startsWith('/')) {
            thumbUrl = `/proxy?url=${encodeURIComponent(thumbUrl)}`;
        }

        if (!thumbUrl) {
            for (const a of articles) {
                if (a && a.image_url) {
                    thumbUrl = a.image_url.startsWith('/') ? a.image_url : `/proxy?url=${encodeURIComponent(a.image_url)}`;
                    break;
                }
            }
        }
        
        // Determine bento size
        let spanClass = "span-12";
        if (idx % 6 === 0) spanClass = "span-12 row-2 featured";
        else if (idx % 3 === 1) spanClass = "span-6";
        else if (idx % 3 === 2) spanClass = "span-6";

        return `
            <article class="bento-card ${spanClass} fade-in">
                ${thumbUrl ? `
                    <div class="bento-thumb-wrap">
                        <a href="/cluster/${cluster.cluster_id}" style="display: block; width: 100%; height: 100%;">
                            <img src="${thumbUrl}" class="bento-thumb" loading="lazy">
                        </a>
                    </div>` : ''}
                
                <div class="bento-body">
                    <div class="bento-meta">
                        <span class="source">${this._esc(main.source)}</span>
                        <span class="time">• ${this._relativeTime(main.created_at)}</span>
                        ${main.category ? `<span class="category" style="background:var(--primary-muted); color:var(--primary); padding:2px 8px; border-radius:6px; font-size:0.65rem; font-weight:800; letter-spacing:0.04em;">${this._esc(main.category)}</span>` : ''}
                        ${cluster.is_breaking ? `<span class="src-badge pulse" style="background:var(--primary); color:#fff; border:none; padding:2px 8px; border-radius:6px; font-weight:800; font-size:0.65rem;">🚨 БРЕЈКИНГ</span>` : ''}
                    </div>
                    
                    <a href="/cluster/${cluster.cluster_id}" class="bento-headline" style="font-size: ${spanClass.includes('featured') ? '2.4rem' : '1.4rem'}; font-weight: ${400 + Math.min(500, Math.floor((cluster.score || 0) * 80))};">
                        ${this._esc(main.title)}
                    </a>
                    
                    <div class="bento-footer">
                        <a href="/cluster/${cluster.cluster_id}" class="count-badge" style="background: var(--primary); color: #fff; font-weight:800; padding: 6px 14px;">ВИДИ РЕЗИМЕ</a>
                        <span class="count-badge" style="background: var(--bg-elevated); border: 1px solid var(--border); padding: 6px 14px;">Вкупно ${count} извори ${cluster.has_balanced ? '· ⚖️ Балансирано' : ''}</span>
                    </div>
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
        const sidebar = document.getElementById('sidebarTrending');
        if (!sidebar) return;
        
        sidebar.innerHTML = (trends || []).slice(0, 8).map(t => `
            <a href="#" class="related-link" style="padding: 8px 0; border-bottom: 1px solid var(--border);" data-search="${encodeURIComponent(t.word)}">
                <span class="src-badge">HOT</span>
                <span>${this._esc(t.word)}</span>
            </a>
        `).join('');
        sidebar.querySelectorAll('.related-link[data-search]').forEach(el => {
            el.addEventListener('click', (e) => { e.preventDefault(); app.setSearch(decodeURIComponent(el.dataset.search)); });
        });
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    },

    init() {
        this._initBackToTop();
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
