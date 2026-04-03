import { _saveSearchToHistory, debounce } from './utils.js';

export function toggleDrawer(show) {
    const drawer = document.getElementById('mobileDrawer');
    const overlay = document.getElementById('drawerOverlay');
    const trigger = document.getElementById('menuTrigger');
    if (!drawer || !overlay) return;
    
    const isOpening = show !== false;
    drawer.classList.toggle('active', isOpening);
    overlay.classList.toggle('active', isOpening);
    document.body.style.overflow = isOpening ? 'hidden' : '';

    if (trigger) {
        trigger.setAttribute('aria-expanded', isOpening);
    }

    if (isOpening) {
        // Focus the close button or first link in drawer
        setTimeout(() => {
            const closeBtn = document.getElementById('drawerClose');
            if (closeBtn) closeBtn.focus();
        }, 100);
    } else {
        // Restore focus to trigger
        if (trigger) trigger.focus();
    }
}

export function _initMobileDrawer() {
    const trigger = document.getElementById('menuTrigger');
    const close = document.getElementById('drawerClose');
    const overlay = document.getElementById('drawerOverlay');
    const drawer = document.getElementById('mobileDrawer');

    if (trigger) trigger.addEventListener('click', () => toggleDrawer(true));
    if (close) close.addEventListener('click', () => toggleDrawer(false));
    if (overlay) overlay.addEventListener('click', () => toggleDrawer(false));

    // Swipe-to-close logic
    if (drawer) {
        let startX = 0;
        let currentX = 0;
        let isDragging = false;

        drawer.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
            isDragging = true;
            drawer.classList.add('dragging');
        }, { passive: true });

        drawer.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            currentX = e.touches[0].clientX;
            const diff = currentX - startX;
            if (diff < 0) { // Only allow swiping left
                drawer.style.transform = `translateX(${diff}px)`;
            }
        }, { passive: true });

        drawer.addEventListener('touchend', (e) => {
            if (!isDragging) return;
            isDragging = false;
            drawer.classList.remove('dragging');
            const diff = currentX - startX;
            drawer.style.transform = ''; // Reset inline style
            
            if (diff < -50) { // Threshold for closing
                toggleDrawer(false);
            }
        });
    }
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
            // Scroll Down
            header.classList.add('hidden');
        } else if (currentScroll < lastScroll && header.classList.contains('hidden')) {
            // Scroll Up
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
    const clear = document.getElementById('searchClear');
    const input = document.getElementById('searchInput');

    if (overlay && close) {
        close.addEventListener('click', () => overlay.classList.remove('active'));
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('active');
        });
    }

    if (input && clear) {
        input.addEventListener('input', () => {
            clear.style.display = input.value ? 'flex' : 'none';
        });
        clear.addEventListener('click', () => {
            input.value = '';
            clear.style.display = 'none';
            input.focus();
        });
    }
}

export function setupNavEvents() {
    // Category Navigation
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.app.setCategory(btn.dataset.topic || '');
        });
    });

    const searchTrigger = document.getElementById('searchTrigger');
    const searchOverlay = document.getElementById('searchOverlay');
    const searchInput = document.getElementById('searchInput');

    if (searchTrigger && searchOverlay) {
        searchTrigger.addEventListener('click', () => {
            searchOverlay.classList.add('active');
            setTimeout(() => searchInput && searchInput.focus(), 50);
        });
    }

    if (searchInput) {
        const liveSearch = debounce((q) => {
            if (q.length >= 2 || q.length === 0) {
                window.app.setSearch(q);
            }
        }, 400);

        searchInput.addEventListener('input', (e) => {
            liveSearch(e.target.value.trim());
        });

        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const q = searchInput.value.trim();
                if (q) {
                    _saveSearchToHistory(q);
                    window.app.setSearch(q);
                    if (searchOverlay) searchOverlay.classList.remove('active');
                }
            }
        });
    }

    // Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
        if (e.key === '/' && searchTrigger && searchOverlay && !searchOverlay.classList.contains('active')) {
            if (document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                e.preventDefault();
                searchTrigger.click();
            }
        }
        if (e.key === 'Escape' && searchOverlay && searchOverlay.classList.contains('active')) {
            searchOverlay.classList.remove('active');
        }
    });
}
