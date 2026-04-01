/**
 * Presek 5.0 - Living Portal Engine (Core Logic)
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
            this.fetchNews();
            this.fetchTrending();
            this.fetchPulse();
            this._setupInfiniteScroll();
        } catch (e) {
            console.error("Critical error during app.init:", e);
        }
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
                if (searchInput) searchInput.focus();
            });
        }

        if (searchClose && searchOverlay) {
            searchClose.addEventListener('click', () => {
                searchOverlay.classList.remove('active');
            });
        }

        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.setSearch(searchInput.value);
                    if (searchOverlay) searchOverlay.classList.remove('active');
                }
            });
        }

        // Theme Toggle
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => {
                const isLight = document.documentElement.classList.toggle('light');
                localStorage.setItem('theme', isLight ? 'light' : 'dark');
                const meta = document.getElementById('themeMeta');
                if (meta) meta.content = isLight ? '#FFFFFF' : '#0A0C0E';
            });
        }

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
        if (!append && container) {
            this.state.page = 0;
            container.innerHTML = '<div class="loading-state" style="padding: 2rem; text-align: center; color: var(--text-muted);">Вчитување вести...</div>';
        }

        const params = new URLSearchParams({
            page: this.state.page,
            page_size: this.state.pageSize
        });

        if (this.state.topic) params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);

        try {
            const res = await fetch(`/api/news?${params}`);
            const data = await res.json();
            
            if (data && data.status === 'success' && data.clusters) {
                UI.renderPage(data.clusters, append);
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
            // Optional: fallback for trending nav if needed
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
            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 1000) {
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
