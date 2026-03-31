/**
 * Presek 4.0 - UI Rendering Module
 */

const UI = {
    renderPage(clusters) {
        const wrap = document.getElementById('pageWrap');
        if (!wrap) return;

        if (!clusters || !clusters.length) {
            wrap.innerHTML = `<div style="text-align:center; padding:100px; color:var(--text-muted)">Нема вести за избраната категорија.</div>`;
            return;
        }

        let html = '<div class="bento-grid">';
        clusters.forEach((c, idx) => {
            let size = 'bento-standard';
            const hasImage = c.articles && c.articles.some(a => a.image_url);
            
            if (idx === 0 && Presek.state.page === 0 && hasImage) size = 'bento-large';
            else if (c.is_breaking && hasImage) size = 'bento-wide';
            else if (idx % 5 === 4 && hasImage) size = 'bento-tall';

            html += this.renderBentoTile(c, size);
        });
        html += '</div>';
        wrap.innerHTML = html;
    },

    renderBentoTile(c, size) {
        const a = c.articles[0];
        const cid = c.cluster_id;
        let clusterImage = null;
        for (let art of c.articles) {
            if (art.image_url) { clusterImage = art.image_url; break; }
        }
        
        // Helper for escaping
        const esc = (str) => {
            if (!str) return '';
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        };

        const imgSrc = clusterImage ? (clusterImage.startsWith('/') ? clusterImage : '/proxy?url=' + encodeURIComponent(clusterImage)) : null;
        const desc = esc(a.description || '').substring(0, 180) + '...';
        const title = esc(a.title);

        let inner = '';
        if (imgSrc) {
            inner = `
                <div class="bento-img-wrap"><img src="${imgSrc}" class="bento-img" loading="lazy"></div>
                <div class="bento-overlay">
                    <div class="bento-meta">
                        ${c.is_breaking ? '<span style="color:#ff3b30">● ВО ЖИВО</span>' : ''}
                        ${c.has_balanced ? '<span style="color:#34c759">✓ СЕОПФАТНО</span>' : ''}
                        <span>${esc(a.source)}</span>
                    </div>
                    <h2 class="bento-title">${title}</h2>
                    ${(size === 'bento-large' || size === 'bento-wide' || size === 'bento-tall') ? `<p class="bento-desc">${desc}</p>` : ''}
                </div>
            `;
        } else {
            inner = `
                <div class="bento-content">
                    <div class="bento-meta"><span>${esc(a.source)}</span></div>
                    <h2 class="bento-title">${title}</h2>
                    <p class="bento-desc" style="color:var(--text-secondary)">${desc.substring(0, 120)}...</p>
                </div>
            `;
        }

        return `<a href="/cluster/${cid}" class="bento-tile ${size} fade-in">${inner}</a>`;
    },

    updateNav() {
        const list = document.getElementById('categoryList');
        if (!list) return;
        
        list.innerHTML = Presek.countries.map(c => `
            <button class="cat-btn ${c.id === Presek.state.category ? 'active' : ''}" onclick="Presek.setCategory('${c.id}')">
                ${c.label}
            </button>
        `).join('');
    },

    updateFilters() {
        const list = document.getElementById('topicList');
        if (!list) return;

        list.innerHTML = Presek.topics.map(t => `
            <div class="trend-tag ${Presek.state.topic === t.id ? 'active' : ''}" onclick="Presek.setTopic('${t.id}')">
                ${t.label}
            </div>
        `).join('');
    },

    showSkeleton() {
        const wrap = document.getElementById('pageWrap');
        if (wrap) {
            wrap.innerHTML = `<div class="bento-grid">
                <div class="skeleton-card bento-large"></div>
                <div class="skeleton-card bento-standard"></div>
                <div class="skeleton-card bento-wide"></div>
                <div class="skeleton-card bento-standard"></div>
                <div class="skeleton-card bento-tall"></div>
            </div>`;
        }
    },

    showError() {
        const wrap = document.getElementById('pageWrap');
        if (wrap) {
            wrap.innerHTML = `<div class="error-state">
                <p>Настана грешка при вчитување на вестите.</p>
                <button class="page-btn" onclick="Presek.fetchNews()">Обиди се повторно</button>
            </div>`;
        }
    },

    showToast(count) {
        const existing = document.getElementById('liveToast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'liveToast';
        toast.style = `
            position: fixed; top: 80px; left: 50%; transform: translateX(-50%);
            background: var(--primary); color: white; padding: 10px 24px;
            border-radius: 30px; font-weight: bold; cursor: pointer; z-index: 1500;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3); font-size: 0.9rem;
        `;
        toast.innerHTML = `✨ ${count} нови вести. Освежи.`;
        toast.onclick = () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            Presek.fetchNews();
            toast.remove();
        };
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 15000);
    },

    initTheme() {
        const theme = localStorage.getItem('theme') || 'dark';
        document.documentElement.classList.toggle('light', theme === 'light');
    }
};

window.UI = UI;
