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
            country: this.state.category,
            sub: this.state.subcategory,
            topic: this.state.topic,
            sentiment: this.state.sentiment,
            q: this.state.query
        });

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
    },

    setTopic(topic) {
        this.state.topic = (this.state.topic === topic) ? '' : topic;
        this.fetchNews();
        UI.updateFilters();
    },

    init() {
        console.log("Presek 4.0 Initialized");
        this.fetchNews();
        UI.initTheme();
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
    }
};

window.Presek = Presek;
document.addEventListener('DOMContentLoaded', () => Presek.init());
