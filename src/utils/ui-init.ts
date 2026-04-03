/**
 * ui-init.ts — Unified UI initializers for Presek.mk
 * Migrated from legacy Vanilla JS modules.
 */

/* ── Theme Management ─────────────────────────────────────────── */

export function initTheme() {
  try {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isLight = saved ? saved === 'light' : !prefersDark;
    
    document.documentElement.classList.toggle('light', isLight);
    document.body.classList.toggle('light', isLight);
    
    const meta = document.getElementById('themeMeta') as HTMLMetaElement | null;
    if (meta) meta.content = isLight ? '#FFFFFF' : '#0A0A0A';
  } catch (e) {
    console.error("Theme init error", e);
  }
}

export function setupThemeEvents() {
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const isLight = document.documentElement.classList.toggle('light');
      try {
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
      } catch (e) {}
      
      // Sync cookie for SSR consistency
      document.cookie = `theme=${isLight ? 'light' : 'dark'}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;

      const meta = document.getElementById('themeMeta') as HTMLMetaElement | null;
      if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';

      document.body.classList.toggle('light', isLight);
      window.dispatchEvent(new Event('themeChanged'));

      themeToggle.style.transform = 'rotate(15deg)';
      setTimeout(() => { themeToggle.style.transform = ''; }, 200);
    });
  }

  const sysTheme = window.matchMedia('(prefers-color-scheme: light)');
  const applySystemTheme = (e: MediaQueryListEvent | MediaQueryList) => {
    let hasSavedTheme = false;
    try {
      hasSavedTheme = !!localStorage.getItem('theme');
    } catch (err) {}

    if (!hasSavedTheme) {
      const isLight = e.matches;
      document.documentElement.classList.toggle('light', isLight);
      document.body.classList.toggle('light', isLight);
      const meta = document.getElementById('themeMeta') as HTMLMetaElement | null;
      if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';
    }
  };
  
  if (sysTheme.addEventListener) sysTheme.addEventListener('change', applySystemTheme);
  else (sysTheme as any).addListener(applySystemTheme);
}

/* ── Navigation & Global Listeners ────────────────────────────── */

export function toggleDrawer(show?: boolean) {
  const drawer = document.getElementById('mobileDrawer');
  const overlay = document.getElementById('drawerOverlay');
  const trigger = document.getElementById('menuTrigger');
  if (!drawer || !overlay) return;
  
  const isOpening = show !== false;
  drawer.classList.toggle('active', isOpening);
  overlay.classList.toggle('active', isOpening);
  document.body.style.overflow = isOpening ? 'hidden' : '';

  if (trigger) trigger.setAttribute('aria-expanded', isOpening.toString());
}

export function initNavigation() {
  // Mobile Drawer
  const menuTrigger = document.getElementById('menuTrigger');
  const drawerClose = document.getElementById('drawerClose');
  const drawerOverlay = document.getElementById('drawerOverlay');

  if (menuTrigger) menuTrigger.addEventListener('click', () => toggleDrawer(true));
  if (drawerClose) drawerClose.addEventListener('click', () => toggleDrawer(false));
  if (drawerOverlay) drawerOverlay.addEventListener('click', () => toggleDrawer(false));

  // Sticky Header
  const header = document.querySelector('.site-header');
  if (header) {
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

  // Back to Top
  const btt = document.getElementById('backToTop');
  if (btt) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 500) {
        btt.style.opacity = '1';
        btt.style.pointerEvents = 'auto';
        btt.style.transform = 'translateY(0)';
      } else {
        btt.style.opacity = '0';
        btt.style.pointerEvents = 'none';
        btt.style.transform = 'translateY(10px)';
      }
    }, { passive: true });
    btt.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

  // Search Overlay
  const searchOverlay = document.getElementById('searchOverlay');
  const searchClose = document.getElementById('searchClose');
  const searchTrigger = document.getElementById('searchTrigger');
  const searchInput = document.getElementById('searchInput') as HTMLInputElement | null;

  if (searchTrigger && searchOverlay) {
    searchTrigger.addEventListener('click', () => {
      searchOverlay.classList.add('active');
      setTimeout(() => searchInput?.focus(), 50);
    });
  }
  if (searchOverlay && searchClose) {
    searchClose.addEventListener('click', () => searchOverlay.classList.remove('active'));
  }

  // Category Buttons (Hijack for SPA navigation)
  document.querySelectorAll('.cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const topic = (btn as HTMLElement).dataset.topic || '';
      const params = new URLSearchParams(window.location.search);
      if (topic) params.set('topic', topic);
      else params.delete('topic');
      params.delete('q');

      const newURL = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
      
      if ((window as any).presekNavigate) {
        (window as any).presekNavigate(newURL);
      } else {
        window.history.pushState({}, '', newURL);
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
      
      document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      toggleDrawer(false);
    });
  });

  // Search Input (Hijack for SPA navigation)
  if (searchInput) {
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        const q = searchInput.value.trim();
        const params = new URLSearchParams(window.location.search);
        if (q) params.set('q', q);
        else params.delete('q');
        
        const newURL = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
        
        if ((window as any).presekNavigate) {
          (window as any).presekNavigate(newURL);
        } else {
          window.history.pushState({}, '', newURL);
          window.dispatchEvent(new PopStateEvent('popstate'));
        }
        
        if (searchOverlay) searchOverlay.classList.remove('active');
      }
    });
  }
}

/* ── Global Link Interception ─────────────────────────────── */

export function setupLinkInterception() {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest('a') as HTMLAnchorElement | null;
    if (anchor && anchor.href && anchor.href.startsWith(window.location.origin)) {
      const path = anchor.getAttribute('href');
      // List of routes handled by React Router
      const isReactRoute = path && (
        path === '/' || 
        path === '/saved' || 
        path === '/briefing' || 
        path === '/stats' || 
        path.startsWith('/cluster/')
      );

      if (isReactRoute && anchor.target !== '_blank') {
        e.preventDefault();
        if ((window as any).presekNavigate) {
          (window as any).presekNavigate(path);
        } else {
          window.history.pushState({}, '', path);
          window.dispatchEvent(new PopStateEvent('popstate'));
        }
      }
    }
  });
}

/* ── Utility ─────────────────────────────────────────────── */

export function updateMacedonianDate() {
  const el = document.getElementById('currentDate');
  if (!el) return;
  const d = new Date();
  const options: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long' };
  let str = d.toLocaleDateString('mk-MK', options);
  // Capitalize first letter
  str = str.charAt(0).toUpperCase() + str.slice(1);
  el.textContent = str;
}
