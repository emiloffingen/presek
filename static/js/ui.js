/**
 * Presek 5.0 — Living Portal Engine
 * Dynamic theming + High Density + Micro-interactions
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

    renderPage(clusters, append = false) {
        const container = document.getElementById('pageWrap');
        if (!container) return;

        if (!append) {
            container.innerHTML = '';
            // Trigger dynamic theme update on fresh load
            if (clusters && clusters.length > 0) {
                this.updateDynamicTheme(clusters);
            }
        }

        if (!clusters || !Array.isArray(clusters) || clusters.length === 0) {
            if (!append) {
                container.innerHTML = `
                    <div class="error-state fade-in">
                        <p>Нема пронајдено вести за избраните критериуми.</p>
                        <button class="page-btn" onclick="location.reload()">Освежи</button>
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
        const main = articles[0] || {};
        const related = articles.slice(1, 6); 
        const count = articles.length;
        
        let thumbUrl = null;
        for (const a of articles) {
            if (a && a.image_url) {
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
                                <span class="src-badge">${this._esc(art.source)}</span>
                                <span class="rel-title">${this._esc(art.title)}</span>
                            </a>
                        </li>`).join('')}
                </ul>
            `;
        }

        return `
            <article class="news-cluster fade-in">
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
                             onerror="this.parentElement.style.display='none'; this.closest('.news-cluster').style.gridTemplateColumns='1fr';">
                    </div>
                ` : ''}
            </article>
        `;
    },

    /* ── Intelligence Features ───────────────────────────── */

    updateDynamicTheme(clusters) {
        const counts = {};
        clusters.forEach(c => {
            const cat = c.articles[0]?.category || 'Сите';
            counts[cat] = (counts[cat] || 0) + 1;
        });

        const dominant = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
        
        // Hue mapping
        const hues = {
            'Македонија': 355,
            'Политика':   355,
            'Економија':  210,
            'Свет':       200,
            'Балкан':     30,
            'Спорт':      145,
            'Технологија': 280,
            'Забава':     320
        };

        const targetHue = hues[dominant] || 355;
        document.documentElement.style.setProperty('--p-h', targetHue);
        console.log("Living Theme: Dominant topic is", dominant, "Hue set to", targetHue);
    },

    renderPulse(entities) {
        const terminal = document.getElementById('entityPulse');
        if (!terminal) return;

        terminal.innerHTML = `
            <div class="pulse-line"><span>>>> SYSTEM READY</span><span class="val">OK</span></div>
            ${entities.slice(0, 15).map(e => `
                <div class="pulse-line" style="cursor:pointer" onclick="app.setSearch('${this._esc(e.word || e.name)}')">
                    <span>${this._esc(e.word || e.name)}</span>
                    <span class="val">${e.count || e.n || ''}</span>
                </div>
            `).join('')}
            <div class="pulse-line" style="opacity:0.4"><span>_</span></div>
        `;
    },

    updateClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
};

setInterval(() => UI.updateClock(), 1000);
UI.updateClock();

window.UI = UI;
