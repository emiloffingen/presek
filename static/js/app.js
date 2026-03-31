/**
 * Presek 4.0 - Core Application Logic
 */

const Presek = {
    state: {
        page: 0,
        pageSize: 50,
        category: '🇲🇰',
        subcategory: '',
        topic: '',
        sentiment: '',
        query: '',
        isFetching: false,
        clusters: [],
        hasMore: true
    },

    countries: [
        { id: '🇲🇰', label: 'Македонија' },
        { id: 'POPULAR', label: 'Популарно' },
        { id: '🇩🇪', label: 'Германија' },
        { id: '🇷🇸', label: 'Србија' },
        { id: '🇺🇸', label: 'САД' },
        { id: '🇧🇬', label: 'Бугарија' },
        { id: '🇬🇷', label: 'Грција' },
        { id: '🇦🇱', label: 'Албанија' },
        { id: '🇨🇭', label: 'Швајцарија' },
        { id: '🇹🇷', label: 'Турција' }
    ],

    topics: [
        { id: '', label: 'Сите Теми' },
        { id: 'Политика', label: 'Политика' },
        { id: 'Економија', label: 'Економија' },
        { id: 'Технологија', label: 'Технологија' },
        { id: 'Спорт', label: 'Спорт' },
        { id: 'Забава', label: 'Забава' },
        { id: 'Здравје', label: 'Здравје' }
    ],

    async fetchNews(isLoadMore = false) {
        if (this.state.isFetching) return;
        this.state.isFetching = true;

        if (!isLoadMore) {
            this.state.page = 0;
            this.state.clusters = [];
            UI.showSkeleton();
        }

        const params = new URLSearchParams({
            page: this.state.page,
            page_size: this.state.pageSize,
            topic: this.state.topic,
            sentiment: this.state.sentiment,
            q: this.state.query
        });

        if (this.state.category === 'POPULAR') {
            params.set('sort', 'popular');
        } else {
            params.set('country', this.state.category);
        }

        try {
            const res = await fetch(`/api/news?${params}`);
            const json = await res.json();
            
            if (json.status === 'success') {
                if (isLoadMore) {
                    this.state.clusters = [...this.state.clusters, ...json.clusters];
                } else {
                    this.state.clusters = json.clusters;
                }
                this.state.hasMore = json.has_more;
                UI.renderPage(this.state.clusters);
            } else {
                UI.showError();
            }
        } catch (e) {
            console.error("Fetch error:", e);
            UI.showError();
        } finally {
            this.state.isFetching = false;
        }
    },

    setCategory(cat) {
        this.state.category = cat;
        this.state.subcategory = '';
        this.state.topic = '';
        this.fetchNews();
        UI.updateNav();
        UI.updateFilters();
    },

    setTopic(topic) {
        this.state.topic = (this.state.topic === topic) ? '' : topic;
        this.fetchNews();
        UI.updateFilters();
    },

    init() {
        console.log("Presek 4.0 Initialized");
        UI.initTheme();
        UI.updateNav();
        UI.updateFilters();
        this.fetchNews();
        LiveUpdates.connect();
    }
};

const LiveUpdates = {
    connect() {
        const source = new EventSource('/api/live');
        source.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'new_articles') UI.showToast(data.count);
        };
        source.onerror = () => {
            source.close();
            setTimeout(() => this.connect(), 10000);
        };
    }
};

window.Presek = Presek;
document.addEventListener('DOMContentLoaded', () => Presek.init());
