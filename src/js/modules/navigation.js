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

export function setupNavEvents() {
    // Category Navigation
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const topic = btn.dataset.topic || '';
            const params = new URLSearchParams(window.location.search);
            if (topic) params.set('topic', topic);
            else params.delete('topic');
            params.delete('q'); // Clear search when changing category

            const newURL = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
            window.history.pushState({}, '', newURL);
            window.dispatchEvent(new PopStateEvent('popstate'));
            
            // Update active state manually for instant feedback
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
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
    setupNavEvents();
    // Re-add other initializers if needed
}
