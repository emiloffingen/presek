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
        isSaved: false,
        isFetching: false,
        hasMore: true
    },

    init() {
        try {
            this._bindEvents();
            this._restoreFromURL();
            this._initPersonalization();
            
            // SSR (Instant Paint) Optimization
            const container = document.getElementById('pageWrap');
            const hasSSR = container && container.querySelector('.news-cluster');
            const isFresh = !this.state.topic && !this.state.query && !this.state.isSaved;

            if (hasSSR && isFresh) {
                console.log("Presek SSR: Content detected, starting infinite scroll from page 1.");
                this.state.page = 1;
            } else {
                this.fetchNews();
            }

            this.fetchTrending();
            this._setupInfiniteScroll();
        } catch (e) {
            console.error("Critical error during app.init:", e);
        }
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
                // Sync cookie so server-side body class stays consistent on next load
                document.cookie = `theme=${isLight ? 'light' : 'dark'}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;

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
        this.state.isSaved = location.pathname === '/saved';
        
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
        let url = params.toString() ? `/?${params}` : '/';
        if (this.state.isSaved) url = '/saved';
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

        // PERCEPTION UPGRADE: Append skeletons immediately if infinite scrolling
        let skeletonBuffer = null;
        if (append && container && window.UI) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = UI._renderSkeletons(3);
            skeletonBuffer = Array.from(tempDiv.children);
            skeletonBuffer.forEach(s => container.appendChild(s));
        }

        // Handle Saved mode (offline/local)
        if (this.state.isSaved) {
            try {
                if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());
                const savedIds = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
                if (savedIds.length === 0) {
                    if (container) container.innerHTML = `<div class="error-state fade-in" style="padding: 4rem; text-align: center; color: var(--text-muted);"><p>Немате зачувано вести.</p></div>`;
                    this.state.isFetching = false;
                    return;
                }
                
                // Fetch full cluster data for these IDs
                const res = await fetch(`/api/news?ids=${savedIds.join(',')}`);
                const data = await res.json();
                if (data && data.clusters) {
                    if (window.UI) UI.renderPage(data.clusters, false, false, false);
                }
                this.state.hasMore = false;
            } catch (e) { console.error(e); }
            this.state.isFetching = false;
            return;
        }

        const params = new URLSearchParams({
            page: this.state.page,
            page_size: this.state.pageSize
        });

        if (this.state.topic) params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);
        
        // Add local interests if browsing home page
        let isPersonalized = false;
        if (!this.state.topic && !this.state.query && !this.state.isSaved) {
            const topCats = this._getTopInterests('topic');
            if (topCats) {
                params.set('follow_topics', topCats);
                isPersonalized = true;
            }
        }

        try {
            const res = await fetch(`/api/news?${params}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            // Remove skeletons
            if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());

            if (data && data.status === 'success' && data.clusters) {
                if (window.UI) UI.renderPage(data.clusters, append, isPersonalized, isSearch);
                this.state.hasMore = data.has_more;
            }
        } catch (e) {
            console.error('Fetch news error:', e);
            if (skeletonBuffer) skeletonBuffer.forEach(s => s.remove());
            if (!append) {
                if (container) container.innerHTML = `<div class="error-state fade-in" style="padding:4rem;text-align:center;color:var(--text-muted);"><p>Грешка при вчитување на вести.</p><button class="cat-btn" style="margin-top:1rem;background:var(--bg-elevated);" onclick="location.reload()">Обиди се повторно</button></div>`;
            }
        } finally {
            this.state.isFetching = false;
        }
    },

    async fetchTrending() {
        try {
            const res = await fetch('/api/trending');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (window.UI) {
                UI.renderTrendingSidebar(data);
                UI.renderPulse(data);
            }
        } catch (e) { console.error('Trending fetch failed:', e); }
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
        const trigger = document.getElementById('scrollTrigger');
        const loader = document.getElementById('feedLoading');
        if (!trigger) return;

        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !this.state.isFetching && this.state.hasMore) {
                if (loader) loader.style.display = 'block';
                this.state.page++;
                this.fetchNews(true).then(() => {
                    if (loader) loader.style.display = 'none';
                });
            }
        }, { rootMargin: '400px' });

        observer.observe(trigger);
    }
};

window.app = app;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}
