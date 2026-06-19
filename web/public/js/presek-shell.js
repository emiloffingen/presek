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

  const bindSearchFab = () => {
    document.querySelectorAll('[data-presek-search-fab]').forEach((fab) => {
      if (!(fab instanceof HTMLButtonElement) || fab.dataset.bound === '1') return;
      fab.dataset.bound = '1';
      fab.addEventListener('click', () => {
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
})();
