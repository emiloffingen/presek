(function presekShell() {
  (function ensureMainContentTarget() {
    const assign = () => {
      const main = document.querySelector('main:not([id])');
      if (main) main.id = 'main-content';
    };
    assign();
    document.addEventListener('astro:page-load', assign);
  })();

  document.addEventListener('astro:before-preparation', () => {
    const bar = document.getElementById('loading-bar');
    if (bar) {
      bar.style.width = '30%';
      bar.style.opacity = '1';
    }
  });

  document.addEventListener('astro:after-preparation', () => {
    const bar = document.getElementById('loading-bar');
    if (bar) {
      bar.style.width = '100%';
      setTimeout(() => {
        bar.style.opacity = '0';
        setTimeout(() => { bar.style.width = '0'; }, 300);
      }, 200);
    }
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { type: 'module' }).catch((err) => {
        console.warn('Service Worker registration failed:', err);
      });
    });

    const dispatchPrefetch = () => {
      if (!navigator.serviceWorker.controller) return;
      const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (conn && (conn.saveData || (conn.effectiveType && conn.effectiveType !== '4g'))) {
        return;
      }
      const clusterUrls = Array.from(document.querySelectorAll('a'))
        .map((a) => a.getAttribute('href'))
        .filter((href) => href && (href.startsWith('/cluster/') || href.startsWith('/mk/cluster/')))
        .map((href) => new URL(href, window.location.origin).pathname);
      const uniqueUrls = [...new Set(clusterUrls)].slice(0, 4);
      if (uniqueUrls.length > 0) {
        navigator.serviceWorker.controller.postMessage({
          type: 'PREFETCH_URLS',
          urls: uniqueUrls,
        });
      }
    };

    const schedulePrefetch = () => {
      const idle = window.requestIdleCallback || ((cb) => window.setTimeout(cb, 1500));
      idle(dispatchPrefetch, { timeout: 4000 });
    };
    document.addEventListener('astro:page-load', schedulePrefetch);
  }

  // PWA install prompt: reveal install buttons only when the browser offers it.
  let deferredInstallPrompt = null;
  function bindPwaInstall() {
    const btns = document.querySelectorAll('[data-pwa-install]');
    if (!btns.length) return;
    if (deferredInstallPrompt) {
      btns.forEach((b) => { b.hidden = false; });
    }
    btns.forEach((btn) => {
      if (btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!deferredInstallPrompt) return;
        const panel = btn.closest('.utility-menu-panel');
        const details = btn.closest('details');
        if (panel && details) details.open = false;
        deferredInstallPrompt.prompt();
        deferredInstallPrompt.userChoice
          .then(() => { deferredInstallPrompt = null; })
          .catch(() => {})
          .finally(() => {
            document.querySelectorAll('[data-pwa-install]').forEach((b) => { b.hidden = true; });
          });
      });
    });
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    document.querySelectorAll('[data-pwa-install]').forEach((b) => { b.hidden = false; });
  });

  window.addEventListener('appinstalled', () => {
    deferredInstallPrompt = null;
    document.querySelectorAll('[data-pwa-install]').forEach((b) => { b.hidden = true; });
  });

  bindPwaInstall();
  document.addEventListener('astro:page-load', bindPwaInstall);

  const bindSearchFab = () => {
    document.querySelectorAll('[data-presek-search-fab]').forEach((fab) => {
      if (!(fab instanceof HTMLElement) || fab.dataset.bound === '1') return;
      fab.dataset.bound = '1';
      fab.addEventListener('click', (e) => {
        e.preventDefault();
        window.__presek_search_open_requested = true;
        window.dispatchEvent(new CustomEvent('presek:open-search'));
      });
    });
  };
  bindSearchFab();
  document.addEventListener('astro:page-load', bindSearchFab);

  function initHeaderScroll() {
    const header = document.getElementById('main-header');
    if (!header) return undefined;

    let lastY = window.scrollY;
    let ticking = false;
    const mobileQuery = window.matchMedia('(max-width: 768px)');

    const update = () => {
      const y = window.scrollY;
      const scrollingUp = y < lastY;
      const isMobile = mobileQuery.matches;

      if (isMobile) {
        header.classList.toggle('header--compact', y > 40);
        header.classList.toggle('header--show-ticker', y > 72 || (scrollingUp && y > 20));
        header.classList.add('header--show-nav');
        header.classList.remove('header--hide-ticker');
      } else {
        const compact = y > 96;
        const showTicker = scrollingUp && y > 24;
        const showNav = scrollingUp && y > 72;
        header.classList.toggle('header--compact', compact);
        header.classList.toggle('header--show-ticker', showTicker);
        header.classList.toggle('header--show-nav', showNav);
        header.classList.remove('header--hide-ticker');
      }

      lastY = y;
      ticking = false;
    };

    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return onScroll;
  }

  let headerScrollHandler = null;
  const bindHeaderScroll = () => {
    if (headerScrollHandler) {
      window.removeEventListener('scroll', headerScrollHandler);
      headerScrollHandler = null;
    }
    headerScrollHandler = initHeaderScroll();
  };
  bindHeaderScroll();
  document.addEventListener('astro:page-load', bindHeaderScroll);

  document.addEventListener('astro:page-load', () => {
    if (!('IntersectionObserver' in window)) return;
    const prefetched = new Set();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const href = entry.target.getAttribute('href');
        if (!href || prefetched.has(href)) return;
        prefetched.add(href);
        fetch(href, { priority: 'low' }).catch(() => {});
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '80px 0px' });
    document.querySelectorAll('a[data-testid="cluster-link"]').forEach((link, index) => {
      if (index < 4) observer.observe(link);
    });
  });

  function initParallax() {
    if (window.innerWidth < 1024) return;
    const parallaxEls = Array.from(document.querySelectorAll('.lead-media-image, .cluster-visual-image'));
    if (parallaxEls.length === 0) return;
    let ticking = false;
    const handleScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        const scrolled = window.scrollY;
        for (const el of parallaxEls) {
          el.style.setProperty('--parallax-y', `${scrolled * 0.15}px`);
        }
        ticking = false;
      });
    };
    if (window._presekParallaxHandler) {
      window.removeEventListener('scroll', window._presekParallaxHandler);
    }
    window._presekParallaxHandler = handleScroll;
    window.addEventListener('scroll', handleScroll, { passive: true });
  }
  initParallax();
  document.addEventListener('astro:page-load', initParallax);

  // Full original text (transparency mode): expandable per article.
  function bindFulltextToggle() {
    if (window.__presekFulltextBound) return;
    window.__presekFulltextBound = true;
    document.addEventListener('click', function (ev) {
      const target = ev.target;
      const btn = target && target.closest ? target.closest('.fulltext-toggle') : null;
      if (!btn) return;
      const wrap = btn.closest('.fulltext-wrap');
      if (!wrap) return;
      const panel = wrap.querySelector('.fulltext-panel');
      const body = wrap.querySelector('.fulltext-body');
      const label = btn.querySelector('.fulltext-toggle-label');
      const expanded = btn.getAttribute('aria-expanded') === 'true';

      if (expanded) {
        btn.setAttribute('aria-expanded', 'false');
        if (panel) panel.hidden = true;
        if (label) label.textContent = btn.dataset.showLabel || '';
        return;
      }
      if (panel) panel.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      if (label) label.textContent = btn.dataset.hideLabel || '';
      if (body && body.dataset.loaded === 'true') return;

      const id = wrap.dataset.articleId;
      if (!id || !body) return;
      body.textContent = wrap.dataset.loading || '';
      body.dataset.loaded = 'error';
      fetch('/api/article/' + encodeURIComponent(id) + '?lang=mk', {
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          if (!r.ok) throw new Error('http ' + r.status);
          return r.json();
        })
        .then(function (data) {
          if (data && data.full_content && data.full_text_allowed !== false) {
            body.textContent = '';
            String(data.full_content)
              .split(/\n{2,}/)
              .forEach(function (raw) {
                const text = raw.trim();
                if (!text) return;
                const p = document.createElement('p');
                p.textContent = text;
                body.appendChild(p);
              });
            body.dataset.loaded = 'true';
          } else {
            body.textContent = wrap.dataset.unavailable || '';
          }
        })
        .catch(function () {
          body.textContent = wrap.dataset.error || '';
        });
    });
  }
  bindFulltextToggle();
  document.addEventListener('astro:page-load', bindFulltextToggle);
})();
