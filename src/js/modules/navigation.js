export function toggleDrawer(show) {
    const drawer = document.getElementById('mobileDrawer');
    const overlay = document.getElementById('drawerOverlay');
    const trigger = document.getElementById('menuTrigger');
    if (!drawer || !overlay) return;
    
    const isOpening = show !== false;
    drawer.classList.toggle('active', isOpening);
    overlay.classList.toggle('active', isOpening);
    document.body.style.overflow = isOpening ? 'hidden' : '';

    if (trigger) trigger.setAttribute('aria-expanded', isOpening);
}

export function _initMobileDrawer() {
    const trigger = document.getElementById('menuTrigger');
    const close = document.getElementById('drawerClose');
    const overlay = document.getElementById('drawerOverlay');
    const drawer = document.getElementById('mobileDrawer');

    if (trigger) trigger.addEventListener('click', () => toggleDrawer(true));
    if (close) close.addEventListener('click', () => toggleDrawer(false));
    if (overlay) overlay.addEventListener('click', () => toggleDrawer(false));
}

export function _initStickyHeader() {
    const header = document.querySelector('.site-header');
    if (!header) return;

    let lastScroll = 0;
    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;
        if (currentScroll <= 0) {
            header.classList.remove('hidden');
            return;
        }
        if (currentScroll > lastScroll && !header.classList.contains('hidden') && currentScroll > 200) {
            header.classList.add('hidden');
        } else if (currentScroll < lastScroll && header.classList.contains('hidden')) {
            header.classList.remove('hidden');
        }
        lastScroll = currentScroll;
    }, { passive: true });
}

export function _initBackToTop() {
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
    btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

export function _initSearchOverlay() {
    const overlay = document.getElementById('searchOverlay');
    const close = document.getElementById('searchClose');
    const trigger = document.getElementById('searchTrigger');
    const input = document.getElementById('searchInput');

    if (trigger && overlay) {
        trigger.addEventListener('click', () => {
            overlay.classList.add('active');
            setTimeout(() => input && input.focus(), 50);
        });
    }

    if (overlay && close) {
        close.addEventListener('click', () => overlay.classList.remove('active'));
    }
}

export function setupNavEvents() {
    // Category Navigation
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const topic = btn.dataset.topic || '';
            const params = new URLSearchParams(window.location.search);
            if (topic) params.set('topic', topic);
            else params.delete('topic');
            params.delete('q');

            const newURL = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
            window.history.pushState({}, '', newURL);
            window.dispatchEvent(new PopStateEvent('popstate'));
            
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            toggleDrawer(false);
        });
    });

    // Search
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const q = searchInput.value.trim();
                const params = new URLSearchParams(window.location.search);
                if (q) params.set('q', q);
                else params.delete('q');
                
                const newURL = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
                window.history.pushState({}, '', newURL);
                window.dispatchEvent(new PopStateEvent('popstate'));
                
                const overlay = document.getElementById('searchOverlay');
                if (overlay) overlay.classList.remove('active');
            }
        });
    }
}

export function initNavigation() {
    _initMobileDrawer();
    _initStickyHeader();
    _initBackToTop();
    _initSearchOverlay();
    setupNavEvents();
}
