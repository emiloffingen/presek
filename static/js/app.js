/**
 * Presek 4.0 - Core Application Logic (Portal Edition)
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
        this._bindEvents();
        this._restoreFromURL();
        this.fetchNews();
        this.fetchTrending();
        this._setupInfiniteScroll();
    },

    _bindEvents() {
        // Category Navigation
        document.querySelectorAll('.cat-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.setCategory(btn.dataset.category);
            });
        });

        // Search
        const searchTrigger = document.getElementById('searchTrigger');
        const searchOverlay = document.getElementById('searchOverlay');
        const searchClose = document.getElementById('searchClose');
        const searchInput = document.getElementById('searchInput');

        if (searchTrigger) {
            searchTrigger.addEventListener('click', () => {
                searchOverlay.classList.add('active');
                searchInput.focus();
            });
        }

        if (searchClose) {
            searchClose.addEventListener('click', () => {
                searchOverlay.classList.remove('active');
            });
        }

        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.setSearch(searchInput.value);
                    searchOverlay.classList.remove('active');
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
            if (e.key === '/' && !searchOverlay.classList.contains('active')) {
                e.preventDefault();
                searchTrigger.click();
            }
            if (e.key === 'Escape' && searchOverlay.classList.contains('active')) {
                searchClose.click();
            }
        });
    },

    _restoreFromURL() {
        const params = new URLSearchParams(location.search);
        this.state.topic = params.get('topic') || '';
        this.state.query = params.get('q') || '';
        
        if (this.state.topic) {
            document.querySelectorAll('.cat-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.category === this.state.topic);
            });
        }
        if (this.state.query && document.getElementById('searchInput')) {
            document.getElementById('searchInput').value = this.state.query;
        }
    },

    _pushState() {
        const params = new URLSearchParams();
        if (this.state.topic && this.state.topic !== 'Сите') params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);
        const url = params.toString() ? `/?${params}` : '/';
        history.pushState(null, '', url);
    },

    async fetchNews(append = false) {
        if (this.state.isFetching) return;
        this.state.isFetching = true;

        if (!append) {
            this.state.page = 0;
            const container = document.getElementById('newsContainer') || document.getElementById('pageWrap');
            if (container) container.innerHTML = '<div class="loading-state">Вчитување...</div>';
        }

        const params = new URLSearchParams({
            page: this.state.page,
            page_size: this.state.pageSize,
            country: '🇲🇰'
        });

        if (this.state.topic && this.state.topic !== 'Сите') params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);

        try {
            const res = await fetch(`/api/news?${params}`);
            const data = await res.json();
            
            if (data.status === 'success') {
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
            UI.renderTrending(data);
        } catch (e) {
            console.error('Fetch trending error:', e);
        }
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
            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 800) {
                this.state.page++;
                this.fetchNews(true);
            }
        });
    }
};

window.app = app;
document.addEventListener('DOMContentLoaded', () => app.init());
