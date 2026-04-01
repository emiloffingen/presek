/**
 * Presek 5.0 - Living Portal Engine (Core Logic)
 * Enhanced with SSR Support, Infinite Scroll, and Local Personalization
 */

const app = {
    state: {
        page: 0,
        pageSize: 30,
        topic: '',
        query: '',
        isFetching: false,
        hasMore: true
    },

    init() {
        try {
            this._bindEvents();
            this._restoreFromURL();
            this._initPersonalization();
            this._initBackToTop();
            
            // SSR (Instant Paint) Optimization
            const container = document.getElementById('pageWrap');
            const hasSSR = container && container.querySelector('.news-cluster');
            const isFresh = !this.state.topic && !this.state.query;

            if (hasSSR && isFresh) {
                console.log("Presek SSR: Content detected, starting infinite scroll from page 1.");
                this.state.page = 1;
            } else {
                this.fetchNews();
            }

            this.fetchTrending();
            this.fetchPulse();
            this._setupInfiniteScroll();
        } catch (e) {
            console.error("Critical error during app.init:", e);
        }
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
    },

    _initPersonalization() {
        // Track interest when clicking news clusters
        document.addEventListener('click', (e) => {
            const clusterLink = e.target.closest('a[href^="/cluster/"]');
            if (clusterLink) {
                const cluster = clusterLink.closest('.news-cluster');
                if (cluster) {
                    const cat = cluster.querySelector('.category')?.textContent.replace('•', '').trim();
                    if (cat) this._trackInterest('topic', cat);
                }
            }
        });
    },

    _trackInterest(type, value) {
        const key = `presek_interests_${type}`;
        let data = {};
        try {
            data = JSON.parse(localStorage.getItem(key) || '{}');
        } catch(e) {}
        data[value] = (data[value] || 0) + 1;
        localStorage.setItem(key, JSON.stringify(data));
    },

    _getTopInterests(type) {
        const key = `presek_interests_${type}`;
        try {
            const data = JSON.parse(localStorage.getItem(key) || '{}');
            return Object.entries(data)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3)
                .map(e => e[0])
                .join(',');
        } catch(e) { return ''; }
    },

    _bindEvents() {
        // Category Navigation
        document.querySelectorAll('.cat-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.setCategory(btn.dataset.topic || '');
            });
        });

        // Search
        const searchTrigger = document.getElementById('searchTrigger');
        const searchOverlay = document.getElementById('searchOverlay');
        const searchClose = document.getElementById('searchClose');
        const searchInput = document.getElementById('searchInput');

        if (searchTrigger && searchOverlay) {
            searchTrigger.addEventListener('click', () => {
                searchOverlay.classList.add('active');
                setTimeout(() => searchInput && searchInput.focus(), 50);
            });
        }

        if (searchClose && searchOverlay) {
            searchClose.addEventListener('click', () => {
                searchOverlay.classList.remove('active');
            });
        }

        // Close search on backdrop click
        if (searchOverlay) {
            searchOverlay.addEventListener('click', (e) => {
                if (e.target === searchOverlay) {
                    searchOverlay.classList.remove('active');
                }
            });
        }

        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const q = searchInput.value.trim();
                    if (q) {
                        this.setSearch(q);
                        if (searchOverlay) searchOverlay.classList.remove('active');
                    }
                }
            });
        }

        // Theme Toggle
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => {
                const isLight = document.documentElement.classList.toggle('light');
                localStorage.setItem('theme', isLight ? 'light' : 'dark');
                
                // Update theme color meta
                const meta = document.getElementById('themeMeta');
                if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';
                
                document.body.classList.toggle('light', isLight);
                
                // Add a small rotation effect to the button
                themeToggle.style.transform = 'rotate(15deg)';
                setTimeout(() => themeToggle.style.transform = '', 200);
            });
        }

        // Auto System Theme Sync
        const sysTheme = window.matchMedia('(prefers-color-scheme: light)');
        const applySystemTheme = (e) => {
            if (!localStorage.getItem('theme')) {
                const isLight = e.matches;
                document.documentElement.classList.toggle('light', isLight);
                document.body.classList.toggle('light', isLight);
                const meta = document.getElementById('themeMeta');
                if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';
            }
        };
        if (sysTheme.addEventListener) sysTheme.addEventListener('change', applySystemTheme);
        else sysTheme.addListener(applySystemTheme); // Legacy support

        // Keyboard shortcuts
        window.addEventListener('keydown', (e) => {
            if (e.key === '/' && searchTrigger && searchOverlay && !searchOverlay.classList.contains('active')) {
                e.preventDefault();
                searchTrigger.click();
            }
            if (e.key === 'Escape' && searchOverlay && searchOverlay.classList.contains('active')) {
                searchOverlay.classList.remove('active');
            }
        });
    },

    _restoreFromURL() {
        const params = new URLSearchParams(location.search);
        this.state.topic = params.get('topic') || '';
        this.state.query = params.get('query') || params.get('q') || '';
        
        document.querySelectorAll('.cat-btn').forEach(btn => {
            btn.classList.toggle('active', (btn.dataset.topic || '') === this.state.topic);
        });
        
        if (this.state.query && document.getElementById('searchInput')) {
            document.getElementById('searchInput').value = this.state.query;
        }
    },

    _pushState() {
        const params = new URLSearchParams();
        if (this.state.topic) params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);
        const url = params.toString() ? `/?${params}` : '/';
        history.pushState(null, '', url);
    },

    async fetchNews(append = false) {
        if (this.state.isFetching) return;
        this.state.isFetching = true;

        const container = document.getElementById('pageWrap');
        const isSearch = !!this.state.query;

        if (!append && container) {
            this.state.page = 0;
            container.innerHTML = `<div class="loading-state" style="padding: 2rem; text-align: center; color: var(--text-muted);">${isSearch ? 'Пребарување...' : 'Вчитување вести...'}</div>`;
        }

        const params = new URLSearchParams({
            page: this.state.page,
            page_size: this.state.pageSize
        });

        if (this.state.topic) params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);
        
        // Add local interests if browsing home page
        let isPersonalized = false;
        if (!this.state.topic && !this.state.query) {
            const topCats = this._getTopInterests('topic');
            if (topCats) {
                params.set('follow_topics', topCats);
                isPersonalized = true;
            }
        }

        try {
            const res = await fetch(`/api/news?${params}`);
            const data = await res.json();
            
            if (data && data.status === 'success' && data.clusters) {
                if (window.UI) UI.renderPage(data.clusters, append, isPersonalized, isSearch);
                this.state.hasMore = data.has_more;
            }
        } catch (e) {
            console.error('Fetch news error:', e);
        } finally {
            this.state.isFetching = false;
        }
    },

    async fetchTrending() {
        try {
            const res = await fetch('/api/trending');
            const data = await res.json();
            if (window.UI) UI.renderTrendingSidebar(data);
        } catch (e) { console.error(e); }
    },

    async fetchPulse() {
        try {
            const res = await fetch('/api/trending');
            const data = await res.json();
            if (window.UI) UI.renderPulse(data);
        } catch (e) { console.error("Pulse fetch failed", e); }
    },

    setCategory(cat) {
        this.state.topic = cat;
        this.state.query = '';
        const inp = document.getElementById('searchInput');
        if (inp) inp.value = '';
        this._pushState();
        this.fetchNews();
    },

    setSearch(q) {
        this.state.query = q;
        this._pushState();
        this.fetchNews();
    },

    _setupInfiniteScroll() {
        window.addEventListener('scroll', () => {
            if (this.state.isFetching || !this.state.hasMore) return;
            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 1200) {
                this.state.page++;
                this.fetchNews(true);
            }
        }, { passive: true });
    }
};

window.app = app;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}
