/**
 * Presek 4.0 - UI Rendering Module
 */

const UI = {
    renderPage(clusters) {
        const wrap = document.getElementById('pageWrap');
        if (!wrap) return;

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
        const imgSrc = clusterImage ? (clusterImage.startsWith('/') ? clusterImage : '/proxy?url=' + encodeURIComponent(clusterImage)) : null;

        let inner = '';
        if (imgSrc) {
            inner = `
                <div class="bento-img-wrap"><img src="${imgSrc}" class="bento-img" loading="lazy"></div>
                <div class="bento-overlay">
                    <div class="bento-meta">
                        ${c.is_breaking ? '<span style="color:#ff3b30">● ВО ЖИВО</span>' : ''}
                        ${c.has_balanced ? '<span style="color:#34c759">✓ СЕОПФАТНО</span>' : ''}
                        <span>${a.source}</span>
                    </div>
                    <h2 class="bento-title">${a.title}</h2>
                </div>
            `;
        } else {
            inner = `
                <div class="bento-content">
                    <div class="bento-meta"><span>${a.source}</span></div>
                    <h2 class="bento-title">${a.title}</h2>
                    <p class="bento-desc">${(a.description || '').substring(0, 120)}...</p>
                </div>
            `;
        }

        return `<a href="/cluster/${cid}" class="bento-tile ${size} fade-in">${inner}</a>`;
    },

    showSkeleton() {
        const wrap = document.getElementById('pageWrap');
        if (wrap) {
            wrap.innerHTML = `<div class="bento-grid">
                <div class="skeleton-card bento-large"></div>
                <div class="skeleton-card bento-standard"></div>
                <div class="skeleton-card bento-wide"></div>
            </div>`;
        }
    },

    showToast(count) {
        const toast = document.createElement('div');
        toast.className = 'live-toast fade-in';
        toast.innerHTML = `✨ ${count} нови вести. Освежи.`;
        toast.onclick = () => location.reload();
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 10000);
    },

    initTheme() {
        const theme = localStorage.getItem('theme') || 'dark';
        document.documentElement.classList.toggle('light', theme === 'light');
    }
};

window.UI = UI;
