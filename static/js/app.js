/**
 * Presek 4.0 - Core Application Logic
 * Macedonia-first edition
 */

const Presek = {
    state: {
        page: 0,
        pageSize: 50,
        topic: '',
        sort: 'recent',
        query: '',
        isFetching: false,
        clusters: [],
        hasMore: true
    },

    topics: [
        { id: '',            label: 'Сите',        icon: '◈' },
        { id: 'trending',    label: 'Популарно',   icon: '↑' },
        { id: 'Политика',    label: 'Политика',    icon: null },
        { id: 'Економија',   label: 'Економија',   icon: null },
        { id: 'Спорт',       label: 'Спорт',       icon: null },
        { id: 'Хроника',     label: 'Хроника',     icon: null },
        { id: 'Технологија', label: 'Технологија', icon: null },
        { id: 'Здравје',     label: 'Здравје',     icon: null },
        { id: 'Забава',      label: 'Забава',       icon: null },
        { id: 'Општество',   label: 'Општество',   icon: null },
    ],

    renderTopicNav() {
        const list = document.getElementById('topicBtnList');
        if (!list) return;
        list.innerHTML = this.topics.map(t => {
            const isPopular    = t.id === 'trending';
            const reallyActive = isPopular
                ? this.state.sort === 'popular'
                : t.id === this.state.topic && this.state.sort !== 'popular';
            const label = t.icon ? `<span class="topic-icon">${t.icon}</span>${t.label}` : t.label;
            return `<button class="topic-btn ${reallyActive ? 'active' : ''}" onclick="Presek.setTopic('${t.id}')">${label}</button>`;
        }).join('');
    },

    // Fix #3: push URL state so back/forward work
    _pushState() {
        const params = new URLSearchParams();
        if (this.state.sort === 'popular')  params.set('sort', 'popular');
        else if (this.state.topic)          params.set('topic', this.state.topic);
        if (this.state.query)               params.set('q', this.state.query);
        const url = params.toString() ? `/?${params}` : '/';
        history.pushState(
            { topic: this.state.topic, sort: this.state.sort, query: this.state.query },
            '',
            url
        );
    },

    async fetchTrending() {
        try {
            const res = await fetch('/api/trending');
            const words = await res.json();
            UI.renderTrending(words);
        } catch (e) {
            const el = document.getElementById('trendingWords');
            if (el) el.innerHTML = '';
        }
    },

    async fetchPulse() {
        try {
            const res = await fetch('/api/sources/pulse');
            const sources = await res.json();
            UI.renderPulse(sources);
        } catch (e) {
            const el = document.getElementById('pulseSources');
            if (el) el.innerHTML = '';
        }
    },

    async fetchNews(isLoadMore = false) {
        if (this.state.isFetching) return;
        this.state.isFetching = true;

        if (!isLoadMore) {
            this.state.page = 0;
            this.state.clusters = [];
            UI.showSkeleton();
        }

        const params = new URLSearchParams({
            page:      this.state.page,
            page_size: this.state.pageSize,
            country:   '🇲🇰',
            q:         this.state.query
        });

        if (this.state.sort === 'popular') {
            params.set('sort', 'popular');
        } else if (this.state.topic) {
            params.set('topic', this.state.topic);
        }

        try {
            const res  = await fetch(`/api/news?${params}`);
            const json = await res.json();

            if (json.status === 'success') {
                this.state.clusters = isLoadMore
                    ? [...this.state.clusters, ...json.clusters]
                    : json.clusters;
                this.state.hasMore = json.has_more;
                UI.renderPage(this.state.clusters);
            } else {
                UI.showError();
            }
        } catch (e) {
            console.error('Fetch error:', e);
            UI.showError();
        } finally {
            this.state.isFetching = false;
        }
    },

    setTopic(id) {
        if (id === 'trending') {
            this.state.sort  = 'popular';
            this.state.topic = '';
        } else {
            this.state.sort  = 'recent';
            this.state.topic = (this.state.topic === id) ? '' : id;
        }
        this._pushState();
        this.fetchNews();
        this.renderTopicNav();
    },

    filterByWord(word) {
        this.state.query = word;
        const inp = document.getElementById('searchInput');
        if (inp) inp.value = word;
        this.state.sort  = 'recent';
        this.state.topic = '';
        this._pushState();
        this.fetchNews();
        this.renderTopicNav();
    },

    _restoreFromURL() {
        const params = new URLSearchParams(location.search);
        this.state.sort  = params.get('sort')  || 'recent';
        this.state.topic = params.get('topic') || '';
        this.state.query = params.get('q')     || '';
        const inp = document.getElementById('searchInput');
        if (inp) inp.value = this.state.query;
    },

    init() {
        // Fix #3: enable native scroll restoration on back/forward
        if ('scrollRestoration' in history) history.scrollRestoration = 'auto';

        UI.initTheme();

        // Restore state from URL (handles direct links and page reload)
        this._restoreFromURL();

        // Fix #3: pop state handler for browser back/forward
        window.addEventListener('popstate', (e) => {
            const s = e.state || {};
            this.state.topic = s.topic || '';
            this.state.sort  = s.sort  || 'recent';
            this.state.query = s.query || '';
            const inp = document.getElementById('searchInput');
            if (inp) inp.value = this.state.query;
            this.fetchNews();
            this.renderTopicNav();
        });

        this.renderTopicNav();
        this.fetchNews();
        this.fetchTrending();
        this.fetchPulse();

        // Refresh trending + pulse every 5 min
        setInterval(() => { this.fetchTrending(); this.fetchPulse(); }, 300000);

        LiveUpdates.connect();
    }
};

// Fix #8: exponential backoff on SSE reconnects (15s → 30s → 60s … cap 5min)
const LiveUpdates = {
    _delay: 15000,

    connect() {
        const source = new EventSource('/api/live');

        source.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'new_articles') UI.showToast(data.count);
            } catch (_) {}
        };

        source.onopen = () => {
            this._delay = 15000; // reset on successful connection
        };

        source.onerror = () => {
            source.close();
            setTimeout(() => this.connect(), this._delay);
            this._delay = Math.min(this._delay * 2, 300000); // cap at 5 min
        };
    }
};

window.Presek = Presek;
document.addEventListener('DOMContentLoaded', () => Presek.init());
