import { appState, uiState } from './modules/state.js';
import * as utils from './modules/utils.js';
import * as theme from './modules/theme.js';
import * as api from './modules/api.js';
import * as uiRender from './modules/ui-render.js';
import * as navigation from './modules/navigation.js';
import * as personalization from './modules/personalization.js';

const app = {
    state: appState,
    init() {
        try {
            theme.initTheme();
            theme.setupThemeEvents();
            navigation.setupNavEvents();
            this._restoreFromURL();
            personalization._initPersonalization();
            api.initLiveUpdates();
            utils._updateMacedonianDate();
            api.fetchWeather();
            
            // SSR (Instant Paint) Optimization
            const container = document.getElementById('newsFeed');
            if (!container) return;

            const isFeedPage = location.pathname === '/' || location.pathname === '/saved';
            const hasSSR = container.querySelector('.news-cluster');
            const isFresh = !this.state.topic && !this.state.query && !this.state.isSaved;

            if (hasSSR && isFresh) {
                console.log("Presek SSR: Content detected, starting infinite scroll from page 1.");
                this.state.page = 1;
            } else if (isFeedPage || (location.pathname === '/' && (this.state.topic || this.state.query))) {
                this.fetchNews();
            }

            this.fetchTrending();
            this._setupInfiniteScroll();
        } catch (e) {
            console.error("Critical error during app.init:", e);
        }
    },

    _restoreFromURL() {
        const params = new URLSearchParams(location.search);
        this.state.topic = params.get('topic') || '';
        this.state.query = params.get('query') || params.get('q') || '';
        this.state.isSaved = location.pathname === '/saved';
        
        this._updateActiveLinks();
        
        if (this.state.query && document.getElementById('searchInput')) {
            document.getElementById('searchInput').value = this.state.query;
        }
    },

    _updateActiveLinks() {
        // Update category buttons
        document.querySelectorAll('.cat-btn').forEach(btn => {
            btn.classList.toggle('active', (btn.dataset.topic || '') === this.state.topic);
        });

        // Update sidebar and drawer links
        document.querySelectorAll('.drawer-nav a, .widget-nav a, .footer-links a').forEach(link => {
            const href = link.getAttribute('href');
            if (href) {
                const isActive = (location.pathname === href && !this.state.topic) || 
                                 (href === '/saved' && this.state.isSaved);
                link.classList.toggle('active', isActive);
            }
        });
    },

    _pushState() {
        const params = new URLSearchParams();
        if (this.state.topic) params.set('topic', this.state.topic);
        if (this.state.query) params.set('q', this.state.query);
        let url = params.toString() ? `/?${params}` : '/';
        if (this.state.isSaved) url = '/saved';
        history.pushState(null, '', url);
        this._updateActiveLinks();
    },

    async fetchNews(append = false) {
        return api.fetchNews(append);
    },

    async fetchTrending() {
        return api.fetchTrending();
    },

    setCategory(cat) {
        this.state.topic = cat;
        this.state.query = '';
        const inp = document.getElementById('searchInput');
        if (inp) inp.value = '';
        this._pushState();
        
        const container = document.getElementById('pageWrap');
        if (container) {
            container.classList.add('transitioning');
            setTimeout(() => {
                this.fetchNews().then(() => {
                    setTimeout(() => container.classList.remove('transitioning'), 50);
                });
            }, 150);
        } else {
            this.fetchNews();
        }
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
    },

    // Utilities exposed via app
    _getTopInterests: utils._getTopInterests,
    showToast: utils.showToast
};

const UI = {
    state: uiState,
    _esc: utils._esc,
    _relativeTime: utils._relativeTime,
    _renderSkeletons: uiRender._renderSkeletons,
    renderPage: uiRender.renderPage,
    updateDynamicTheme: uiRender.updateDynamicTheme,
    renderPulse: uiRender.renderPulse,
    renderTrendingSidebar: uiRender.renderTrendingSidebar,
    toggleDrawer: navigation.toggleDrawer,
    
    isBookmarked(clusterId) {
        try {
            const saved = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
            return saved.includes(clusterId);
        } catch (e) { return false; }
    },

    async shareCluster(title) {
        const shareData = {
            title: title || 'Пресек',
            text: title,
            url: window.location.href
        };

        try {
            if (navigator.share) {
                await navigator.share(shareData);
            } else {
                await navigator.clipboard.writeText(window.location.href);
                alert('Линкот е ископиран во таблата.');
            }
        } catch (err) {
            console.error('Share error:', err);
        }
    },

    toggleBookmark(event, clusterId) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        try {
            let saved = JSON.parse(localStorage.getItem('presek_saved_clusters') || '[]');
            const idx = saved.indexOf(clusterId);
            const isAdding = idx === -1;

            if (isAdding) {
                saved.push(clusterId);
            } else {
                saved.splice(idx, 1);
            }
            
            localStorage.setItem('presek_saved_clusters', JSON.stringify(saved));

            // Update UI globally
            document.querySelectorAll(`[onclick*="'${clusterId}'"]`).forEach(btn => {
                if (btn.classList.contains('bookmark-btn')) {
                    btn.classList.toggle('active', isAdding);
                    const svg = btn.querySelector('svg');
                    if (svg) svg.setAttribute('fill', isAdding ? 'currentColor' : 'none');
                    btn.title = isAdding ? 'Отстрани од зачувани' : 'Зачувај за подоцна';
                }
            });

            // If we are on the saved page, removing should trigger a refresh
            if (!isAdding && location.pathname === '/saved') {
                app.fetchNews();
            }

        } catch (e) { console.error("Bookmark toggle error:", e); }
    },

    updateClock: utils.updateClock,
    
    init() {
        try { utils._renderSearchHistory(); } catch(e) {}
        try { navigation._initBackToTop(); } catch(e) { console.error("BackToTop init error", e); }
        try { navigation._initMobileDrawer(); } catch(e) { console.error("MobileDrawer init error", e); }
        try { navigation._initSearchOverlay(); } catch(e) { console.error("SearchOverlay init error", e); }
        try { personalization._initReadingToolkit(); } catch(e) { console.error("ReadingToolkit init error", e); }
        try { personalization._initProgressBar(); } catch(e) { console.error("ProgressBar init error", e); }
        try { personalization._initPrivacyBanner(); } catch(e) { console.error("PrivacyBanner init error", e); }
        try { navigation._initStickyHeader(); } catch(e) { console.error("StickyHeader init error", e); }
    }
};

// Global Exposure for inline handlers and legacy scripts
window.app = app;
window.UI = UI;
window.isFollowing = utils.isFollowing;
window.toggleFollow = utils.toggleFollow;

// Initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        UI.init();
        app.init();
    });
} else {
    UI.init();
    app.init();
}

// Tick the clock
setInterval(() => UI.updateClock(), 1000);
UI.updateClock();
