/**
 * Presek 4.0 — UI Rendering Module (Portal High-Density)
 */

const UI = {

    /* ── Helpers ─────────────────────────────────────────── */

    _esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    },

    _relativeTime(dateStr) {
        const d = new Date(dateStr);
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return 'сега';
        if (diff < 3600) return `${Math.floor(diff / 60)}м`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}ч`;
        return d.toLocaleDateString('mk-MK', { day: 'numeric', month: 'short' });
    },

    /* ── Core Rendering ──────────────────────────────────── */

    renderPage(clusters, append = false) {
        const container = document.getElementById('newsContainer') || document.getElementById('pageWrap');
        if (!container) return;

        if (!append) container.innerHTML = '';

        if (!clusters || clusters.length === 0) {
            if (!append) {
                container.innerHTML = `
                    <div class="error-state fade-in">
                        <p>Нема пронајдено вести за избраните критериуми.</p>
                        <button class="page-btn" onclick="location.reload()">Освежи</button>
                    </div>`;
            }
            return;
        }

        clusters.forEach((cluster, idx) => {
            const html = this._renderCluster(cluster, idx);
            container.insertAdjacentHTML('beforeend', html);
        });
    },

    _renderCluster(cluster, idx) {
        const main = cluster.articles[0];
        const related = cluster.articles.slice(1, 6); // Top 5 related
        const count = cluster.articles.length;
        
        let thumbUrl = null;
        for (const a of cluster.articles) {
            if (a.image_url) {
                thumbUrl = a.image_url.startsWith('/') ? a.image_url : `/proxy?url=${encodeURIComponent(a.image_url)}`;
                break;
            }
        }
        
        let relatedHtml = '';
        if (related.length > 0) {
            relatedHtml = `
                <ul class="cluster-related">
                    ${related.map(art => `
                        <li>
                            <a href="/cluster/${cluster.cluster_id}" class="related-link">
                                <span class="src-name">${this._esc(art.source)}</span>
                                <span class="rel-title">${this._esc(art.title)}</span>
                            </a>
                        </li>
                    `).join('')}
                </ul>
            `;
        }

        return `
            <article class="news-cluster fade-in" style="animation-delay: ${idx * 0.05}s">
                <div class="cluster-main">
                    <div class="cluster-meta">
                        <span class="source">${this._esc(main.source)}</span>
                        <span class="time">• ${this._relativeTime(main.created_at)}</span>
                        ${main.category ? `<span class="category">• ${this._esc(main.category)}</span>` : ''}
                    </div>
                    
                    <a href="/cluster/${cluster.cluster_id}" class="cluster-headline">
                        ${this._esc(main.title)}
                    </a>
                    
                    ${relatedHtml}
                    
                    <div class="cluster-footer">
                        <span class="count-badge">${count} вести</span>
                        <a href="/cluster/${cluster.cluster_id}" class="count-badge" style="background: var(--primary); color: #fff;">Резиме</a>
                    </div>
                </div>
                
                ${thumbUrl ? `
                    <div class="cluster-thumb-wrap">
                        <img src="${thumbUrl}" class="cluster-thumb" loading="lazy" 
                             onerror="this.closest('.cluster-thumb-wrap').style.display='none'; this.closest('.news-cluster').style.gridTemplateColumns='1fr';">
                    </div>
                ` : ''}
            </article>
        `;
    },

    /* ── Sidebar & Widgets ──────────────────────────────── */

    renderTrending(trends) {
        const sidebar = document.getElementById('sidebarTrending');
        if (!sidebar) return;
        
        sidebar.innerHTML = (trends || []).slice(0, 10).map(t => `
            <a href="#" class="trending-item" onclick="if(window.app) app.setSearch('${this._esc(t.word)}'); return false;">
                #${this._esc(t.word)}
            </a>
        `).join('');
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        const now = new Date();
        el.textContent = now.toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
    }
};

// Initial clock update
setInterval(() => UI.updateClock(), 1000);
UI.updateClock();

window.UI = UI;
