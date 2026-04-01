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

    renderPage(clusters, append = false, isPersonalized = false) {
        const container = document.getElementById('pageWrap');
        if (!container) return;

        if (!append) {
            // Smoothly clear container without jump
            container.innerHTML = '';
            
            if (isPersonalized) {
                container.innerHTML = `
                    <div class="personalization-notice fade-in">
                        <span class="p-icon">✨</span> ПЕРСОНАЛИЗИРАН ИЗБОР ЗА ВАС
                    </div>`;
            }

            if (clusters && clusters.length > 0) {
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
        
        // With extreme backend thresholds, all articles in a cluster are the same news.
        const sameNews = articles.slice(1, 7); 
        const count = articles.length;
        
        let thumbUrl = null;
        for (const a of articles) {
            if (a && a.image_url) {
                thumbUrl = a.image_url.startsWith('/') ? a.image_url : `/proxy?url=${encodeURIComponent(a.image_url)}`;
                break;
            }
        }
        
        let sameHtml = '';
        if (sameNews.length > 0) {
            sameHtml = `
                <div class="cluster-tier-label">ИСТАТА ВЕСТ ОД ДРУГИ ИЗВОРИ:</div>
                <ul class="cluster-related same-tier">
                    ${sameNews.map(art => `
                        <li>
                            <a href="/cluster/${cluster.cluster_id}" class="related-link">
                                <span class="src-badge">${this._esc(art.source)}</span>
                                <span class="rel-title">${this._esc(art.title)}</span>
                            </a>
                        </li>`).join('')}
                </ul>`;
        }

        return `
            <article class="news-cluster fade-in">
                <div class="cluster-main">
                    <div class="cluster-meta">
                        <span class="source">${this._esc(main.source)}</span>
                        <span class="time">• ${this._relativeTime(main.created_at)}</span>
                        ${main.category ? `<span class="category">• ${this._esc(main.category)}</span>` : ''}
                        ${main.distance !== undefined ? `<span class="src-badge" style="background:var(--accent); color:#fff; border:none">СЕМАНТИЧКО СОВПАЃАЊЕ</span>` : ''}
                        ${count === 1 ? `<span class="src-badge" style="background:var(--primary-muted); color:var(--primary); border:1px solid var(--primary)">УНИКАТНО</span>` : ''}
                    </div>
                    
                    <a href="/cluster/${cluster.cluster_id}" class="cluster-headline">
                        ${this._esc(main.title)}
                    </a>
                    
                    ${sameHtml}
                    
                    <div class="cluster-footer">
                        <span class="count-badge">${count} извори</span>
                        <a href="/cluster/${cluster.cluster_id}" class="count-badge" style="background: var(--primary); color: #fff;">ВИДИ РЕЗИМЕ</a>
                    </div>
                </div>
                
                ${thumbUrl ? `
                    <div class="cluster-thumb-wrap">
                        <img src="${thumbUrl}" class="cluster-thumb" loading="lazy" 
                             onerror="this.parentElement.style.display='none'; this.closest('.news-cluster').style.gridTemplateColumns='1fr';">
                    </div>` : ''}
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
            <span class="ticker-item" onclick="app.setSearch('${this._esc(e.word || e.name)}')">
                #${this._esc(e.word || e.name)} <span class="val">${e.count || e.n || ''}</span>
            </span>
        `).join('');
    },

    renderTrendingSidebar(trends) {
        const sidebar = document.getElementById('sidebarTrending');
        if (!sidebar) return;
        
        sidebar.innerHTML = (trends || []).slice(0, 8).map(t => `
            <a href="#" class="related-link" style="padding: 8px 0; border-bottom: 1px solid var(--border);" onclick="app.setSearch('${this._esc(t.word)}'); return false;">
                <span class="src-badge">HOT</span>
                <span>${this._esc(t.word)}</span>
            </a>
        `).join('');
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    }
};

setInterval(() => UI.updateClock(), 1000);
UI.updateClock();

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
