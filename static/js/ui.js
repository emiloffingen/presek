/**
 * Presek 4.0 — UI Rendering Module
 * Editorial layout: Hero → Featured row → Compact list
 */

const UI = {

    /* ── Helpers ─────────────────────────────────────────── */

    _esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    },

    _hue(str) {
        let h = 0;
        for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h);
        return Math.abs(h) % 360;
    },

    _imgSrc(url) {
        if (!url) return null;
        return url.startsWith('/') ? url : '/proxy?url=' + encodeURIComponent(url);
    },

    _firstImage(articles) {
        for (const a of articles) { if (a.image_url) return a.image_url; }
        return null;
    },

    _titleWords(title) {
        return new Set((title || '').toLowerCase().split(/\s+/).filter(w => w.length > 3));
    },

    _isDuplicate(words, seen) {
        if (!words.size) return false;
        for (const s of seen) {
            const overlap = [...words].filter(w => s.has(w)).length;
            if (overlap / Math.max(words.size, s.size, 1) > 0.6) return true;
        }
        return false;
    },

    // Fix #1: called by onerror on broken images in bento-era markup (kept for compatibility)
    _noImgFallback(img) {
        const tile = img.closest('.bento-tile');
        if (!tile) return;
        const hue     = tile.dataset.srcHue     || '0';
        const initial = tile.dataset.srcInitial || '?';
        const wrap    = img.closest('.bento-img-wrap');
        const overlay = tile.querySelector('.bento-overlay');
        if (wrap) wrap.remove();
        if (overlay) {
            overlay.classList.remove('bento-overlay');
            overlay.classList.add('bento-content', 'bento-no-img');
            tile.style.setProperty('--src-hue', hue);
            const mark = document.createElement('div');
            mark.className = 'bento-src-mark';
            mark.setAttribute('aria-hidden', 'true');
            mark.textContent = initial;
            overlay.insertBefore(mark, overlay.firstChild);
        }
    },

    /* ── Deduplication ───────────────────────────────────── */

    _dedupe(clusters) {
        const breaking = clusters.filter(c => c.is_breaking);
        const rest     = clusters.filter(c => !c.is_breaking);
        const ordered  = [...breaking, ...rest];
        const seen     = [];
        return ordered.filter(c => {
            const words = this._titleWords(c.articles[0]?.title || '');
            if (this._isDuplicate(words, seen)) return false;
            if (words.size) seen.push(words);
            return true;
        });
    },

    /* ── Page renderer ───────────────────────────────────── */

    renderPage(clusters) {
        const wrap = document.getElementById('pageWrap');
        if (!wrap) return;

        if (!clusters || !clusters.length) {
            wrap.innerHTML = `<div class="empty-state">Нема вести за избраната тема.</div>`;
            this._setLoadMore(false);
            return;
        }

        const deduped = this._dedupe(clusters);
        if (!deduped.length) {
            wrap.innerHTML = `<div class="empty-state">Нема вести за избраната тема.</div>`;
            this._setLoadMore(false);
            return;
        }

        let html = '<div class="editorial-grid">';

        // 1. Hero — first story
        html += this._renderHero(deduped[0]);

        // 2. Featured row — next 3 stories
        const featured = deduped.slice(1, 4);
        if (featured.length) {
            html += `<div class="ed-featured-row">`;
            featured.forEach(c => { html += this._renderFeatured(c); });
            html += `</div>`;
        }

        // 3. Compact list — everything else
        const rest = deduped.slice(4);
        if (rest.length) {
            html += `<div class="ed-section-rule"><span class="ed-section-label">Повеќе Вести</span></div>`;
            html += `<div class="ed-list-grid">`;
            rest.forEach(c => { html += this._renderListItem(c); });
            html += `</div>`;
        }

        html += '</div>';
        wrap.innerHTML = html;
        this._setLoadMore(Presek.state.hasMore);
    },

    /* ── Hero ─────────────────────────────────────────────── */

    _renderHero(c) {
        const a       = c.articles[0];
        const cid     = c.cluster_id;
        const rawImg  = this._firstImage(c.articles);
        const imgSrc  = this._imgSrc(rawImg);
        const hue     = this._hue(a.source || '');
        const initial = (a.source || 'П')[0].toUpperCase();

        const title   = this._esc(a.title || '');
        const rawDesc = (a.description || '').replace(/<[^>]*>/g, '').trim();
        const desc    = this._esc(rawDesc.length > 300 ? rawDesc.slice(0, 300) + '…' : rawDesc);
        const cat     = this._esc(a.category || a.topic || '');
        const srcLabel= c.articles.length > 1
            ? `${c.articles.length} извори`
            : this._esc(a.source || '');

        const breakBadge = c.is_breaking
            ? `<span class="ed-live-badge">● ВО ЖИВО</span> ` : '';

        const imgBlock = imgSrc
            ? `<div class="ed-hero-img">
                   <img src="${imgSrc}" alt="${title}" loading="eager"
                        onerror="this.closest('.ed-hero-img').remove();">
               </div>`
            : `<div class="ed-hero-no-img" style="--ed-hue:${hue}" aria-hidden="true">
                   <span class="ed-hero-initial">${initial}</span>
               </div>`;

        return `<a href="/cluster/${cid}" class="ed-hero fade-in" data-ed-hue="${hue}">
            ${imgBlock}
            <div class="ed-hero-body">
                ${cat || c.is_breaking ? `<div class="ed-category">${breakBadge}${cat}</div>` : ''}
                <h2 class="ed-hero-headline">${title}</h2>
                ${desc ? `<p class="ed-hero-desc">${desc}</p>` : ''}
                <div class="ed-byline"><span>${srcLabel}</span></div>
            </div>
        </a>`;
    },

    /* ── Featured card ────────────────────────────────────── */

    _renderFeatured(c) {
        const a      = c.articles[0];
        const cid    = c.cluster_id;
        const rawImg = this._firstImage(c.articles);
        const imgSrc = this._imgSrc(rawImg);
        const hue    = this._hue(a.source || '');
        const initial= (a.source || 'П')[0].toUpperCase();

        const title    = this._esc(a.title || '');
        const cat      = this._esc(a.category || a.topic || '');
        const srcLabel = c.articles.length > 1
            ? `${c.articles.length} извори`
            : this._esc(a.source || '');

        const breakBadge = c.is_breaking
            ? `<span class="ed-live-badge">● ВО ЖИВО</span> ` : '';

        const imgBlock = imgSrc
            ? `<div class="ed-feat-img">
                   <img src="${imgSrc}" alt="${title}" loading="lazy"
                        onerror="this.closest('.ed-feat-img').remove();">
               </div>`
            : `<div class="ed-feat-no-img" style="--ed-hue:${hue}">${initial}</div>`;

        return `<a href="/cluster/${cid}" class="ed-featured fade-in">
            ${imgBlock}
            <div class="ed-feat-body">
                ${cat || c.is_breaking ? `<div class="ed-category">${breakBadge}${cat}</div>` : ''}
                <h3 class="ed-feat-headline">${title}</h3>
                <div class="ed-byline"><span>${srcLabel}</span></div>
            </div>
        </a>`;
    },

    /* ── List item ────────────────────────────────────────── */

    _renderListItem(c) {
        const a      = c.articles[0];
        const cid    = c.cluster_id;
        const rawImg = this._firstImage(c.articles);
        const imgSrc = this._imgSrc(rawImg);

        const title    = this._esc(a.title || '');
        const cat      = this._esc(a.category || a.topic || '');
        const srcLabel = c.articles.length > 1
            ? `${c.articles.length} извори`
            : this._esc(a.source || '');

        const breakBadge = c.is_breaking
            ? `<span class="ed-live-badge">● ВО ЖИВО</span> ` : '';

        const thumb = imgSrc
            ? `<img src="${imgSrc}" class="ed-list-thumb" loading="lazy" alt=""
                    onerror="this.remove();">`
            : '';

        return `<a href="/cluster/${cid}" class="ed-list-item fade-in">
            <div class="ed-list-body">
                ${cat || c.is_breaking ? `<div class="ed-category">${breakBadge}${cat}</div>` : ''}
                <h3 class="ed-list-headline">${title}</h3>
                <div class="ed-byline"><span>${srcLabel}</span></div>
            </div>
            ${thumb}
        </a>`;
    },

    /* ── Infrastructure ───────────────────────────────────── */

    _setLoadMore(show) {
        const el = document.getElementById('loadMoreWrap');
        if (el) el.style.display = show ? 'flex' : 'none';
    },

    renderTrending(words) {
        const el = document.getElementById('trendingWords');
        if (!el) return;
        el.innerHTML = '';
        if (!words || !words.length) return;
        words.slice(0, 20).forEach(w => {
            const word = typeof w === 'object' ? w.word : w;
            const btn = document.createElement('button');
            btn.className = 'trend-word';
            btn.textContent = word;
            btn.addEventListener('click', () => Presek.filterByWord(word));
            el.appendChild(btn);
        });
    },

    renderPulse(sources) {
        const el = document.getElementById('pulseSources');
        if (!el) return;
        if (!sources || !sources.length) { el.innerHTML = ''; return; }
        const max = sources[0]?.count || 1;
        el.innerHTML = sources.slice(0, 8).map(s => {
            const pct  = Math.round((s.count / max) * 100);
            const heat = pct > 75 ? 'pulse-hot' : pct > 40 ? 'pulse-warm' : 'pulse-cool';
            const d    = document.createElement('div');
            d.textContent = s.source;
            return `<div class="pulse-chip ${heat}" title="${s.count} написи денес">
                <span class="pulse-name">${d.innerHTML}</span>
                <span class="pulse-count">${s.count}</span>
            </div>`;
        }).join('');
    },

    showSkeleton() {
        const wrap = document.getElementById('pageWrap');
        if (!wrap) return;
        this._setLoadMore(false);
        wrap.innerHTML = `
            <div class="editorial-grid">
                <div class="ed-hero-skel">
                    <div class="skeleton-box" style="width:100%;aspect-ratio:16/7;margin-bottom:var(--space-lg);border-radius:2px"></div>
                    <div class="skeleton-box" style="width:80px;height:11px;margin-bottom:var(--space-sm)"></div>
                    <div class="skeleton-box" style="width:80%;height:40px;margin-bottom:8px"></div>
                    <div class="skeleton-box" style="width:55%;height:40px;margin-bottom:var(--space-md)"></div>
                    <div class="skeleton-box" style="width:100%;height:17px;margin-bottom:6px"></div>
                    <div class="skeleton-box" style="width:70%;height:17px;margin-bottom:var(--space-sm)"></div>
                    <div class="skeleton-box" style="width:100px;height:11px"></div>
                </div>
                <div class="ed-featured-row">
                    ${[1,2,3].map(() => `<div>
                        <div class="skeleton-box" style="width:100%;aspect-ratio:3/2;margin-bottom:var(--space-md);border-radius:2px"></div>
                        <div class="skeleton-box" style="width:60px;height:10px;margin-bottom:8px"></div>
                        <div class="skeleton-box" style="width:95%;height:16px;margin-bottom:5px"></div>
                        <div class="skeleton-box" style="width:70%;height:16px;margin-bottom:var(--space-sm)"></div>
                        <div class="skeleton-box" style="width:80px;height:10px"></div>
                    </div>`).join('')}
                </div>
            </div>`;
    },

    showError() {
        const wrap = document.getElementById('pageWrap');
        if (!wrap) return;
        this._setLoadMore(false);
        wrap.innerHTML = `
            <div class="error-state">
                <p>Настана грешка при вчитување на вестите.</p>
                <button class="page-btn" onclick="Presek.fetchNews()">Обиди се повторно</button>
            </div>`;
    },

    showToast(count) {
        const existing = document.getElementById('liveToast');
        if (existing) existing.remove();
        const toast = document.createElement('div');
        toast.id        = 'liveToast';
        toast.className = 'live-toast fade-in';
        toast.textContent = `${count} нов${count === 1 ? 'а вест' : 'и вести'} — освежи`;
        toast.onclick = () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            Presek.fetchNews();
            toast.remove();
        };
        document.body.appendChild(toast);
        setTimeout(() => { if (toast.parentNode) toast.remove(); }, 15000);
    },

    initTheme() {
        const theme = localStorage.getItem('theme') || 'dark';
        document.documentElement.classList.toggle('light', theme === 'light');
    }
};

const AI = {
    toggleSheet(show) {
        const sheet = document.getElementById('aiSheet');
        if (sheet) sheet.classList.toggle('active', show);
    },

    async ask(query = null) {
        const input = document.getElementById('aiInput');
        const q = query || input?.value?.trim();
        if (!q) return;
        if (input) input.value = '';
        const responseEl = document.getElementById('aiResponse');
        if (responseEl) responseEl.innerHTML = '<div style="color:var(--text-muted);font-size:0.9rem">Пребарувам…</div>';
        this.toggleSheet(true);
        try {
            const clusterId = window.location.pathname.split('/').pop();
            const res = await fetch('/api/chat_cluster', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cluster_id: clusterId, query: q })
            });
            const data = await res.json();
            if (responseEl) {
                responseEl.innerHTML = '';
                if (data.error) {
                    responseEl.innerHTML = `<p style="color:var(--primary)">Грешка: ${this._esc(data.error)}</p>`;
                } else {
                    const text = data.response || '';
                    const paragraphs = text.split('\n\n').filter(p => p.trim());
                    responseEl.innerHTML = '';
                    paragraphs.forEach(para => {
                        const p = document.createElement('p');
                        p.style.marginBottom = 'var(--space-sm)';
                        p.innerHTML = para
                            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                            .replace(/\n/g, '<br>');
                        responseEl.appendChild(p);
                    });
                }
            }
        } catch (e) {
            if (responseEl) responseEl.innerHTML = '<p style="color:var(--primary)">Серверот не одговара.</p>';
        }
    }
};

window.UI = UI;
window.AI = AI;
