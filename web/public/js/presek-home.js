(function presekHome() {
  'use strict';

  function readJson(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent || '');
    } catch (_) {
      return fallback;
    }
  }

  function syncHomeModeDock(root) {
    var dock = document.querySelector('[data-home-mode-dock]');
    if (!dock || !root) return;
    var expanded = root.classList.contains('home-analysis-expanded');
    var dailyBtn = dock.querySelector('[data-home-mode-daily]');
    var analizaBtn = dock.querySelector('[data-home-mode-analiza]');
    if (dailyBtn) {
      dailyBtn.classList.toggle('is-active', !expanded);
      dailyBtn.setAttribute('aria-pressed', expanded ? 'false' : 'true');
    }
    if (analizaBtn) {
      analizaBtn.classList.toggle('is-active', expanded);
      analizaBtn.setAttribute('aria-pressed', expanded ? 'true' : 'false');
    }
  }

  function initHomepageSession() {
    var root = document.querySelector('[data-home-session-root]');
    if (!root) return;
    var visitKey = 'homepage-visit-count';
    var expandedKey = 'homepage-analysis-expanded';
    var visits = 0;
    var expanded = '0';
    try {
      visits = Number(localStorage.getItem(visitKey) || '0');
      expanded = localStorage.getItem(expandedKey);
    } catch (_) {}
    if (visits < 1) root.classList.add('home-first-session');
    if (expanded === '1') {
      root.classList.add('home-analysis-expanded');
    }
    syncHomeModeDock(root);
    try {
      localStorage.setItem(visitKey, String(visits + 1));
    } catch (_) {}
  }

  function expandHomeAnalysis() {
    var root = document.querySelector('[data-home-session-root]');
    if (!root) return;
    root.classList.add('home-analysis-expanded');
    root.classList.remove('home-first-session');
    try {
      localStorage.setItem('homepage-analysis-expanded', '1');
    } catch (_) {}
    syncHomeModeDock(root);
    document.querySelector('.homepage-analiza-only')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function collapseHomeAnalysis() {
    var root = document.querySelector('[data-home-session-root]');
    if (!root) return;
    root.classList.remove('home-analysis-expanded');
    try {
      localStorage.removeItem('homepage-analysis-expanded');
    } catch (_) {}
    syncHomeModeDock(root);
    var target = document.querySelector('.lead-wrapper') || document.querySelector('#home-unified-feed');
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function bindHomeModeDock() {
    var dock = document.querySelector('[data-home-mode-dock]');
    if (!dock || dock.dataset.bound) return;
    dock.dataset.bound = '1';
    dock.querySelector('[data-home-mode-daily]')?.addEventListener('click', collapseHomeAnalysis);
    dock.querySelector('[data-home-mode-analiza]')?.addEventListener('click', expandHomeAnalysis);
  }

  function homeDetailsDefaults() {
    var DETAIL_SELECTORS = [
      '.home-mobile-stats-details',
      '[data-synthesis-band]',
      '[data-consensus-band]',
      '[data-perspectives-band]',
      '[data-radar-band]',
      '[data-trending-strip]',
      '[data-live-strip]',
    ];

    function bindToggleMemory() {
      DETAIL_SELECTORS.forEach(function (selector) {
        var details = document.querySelector(selector);
        if (!details || details.dataset.bound) return;
        details.dataset.bound = '1';
        details.addEventListener('toggle', function () {
          details.dataset.userToggled = '1';
        });
      });
    }

    function applyStatsDefaults() {
      var details = document.querySelector('.home-mobile-stats-details');
      if (!details || details.dataset.userToggled) return;
      if (window.matchMedia('(min-width: 769px)').matches) {
        details.setAttribute('open', '');
      } else {
        details.removeAttribute('open');
      }
    }

    function applyAnalizaDefaults() {
      var root = document.querySelector('[data-home-session-root]');
      var isPregledView = document.querySelector('.home-page-variant-pregled');
      if (!isPregledView && !(root && root.classList.contains('home-analysis-expanded'))) return;
      var isDesktop = window.matchMedia('(min-width: 769px)').matches;

      function openUnlessToggled(selector, forceOpen) {
        var details = document.querySelector(selector);
        if (!details || details.dataset.userToggled) return;
        if (forceOpen || isDesktop) details.setAttribute('open', '');
      }

      openUnlessToggled('[data-synthesis-band]', true);
      if (isDesktop) {
        openUnlessToggled('[data-consensus-band]');
      }
    }

    bindToggleMemory();
    applyStatsDefaults();
    applyAnalizaDefaults();
  }

  function homeExpandAnalysis() {
    var button = document.querySelector('[data-expand-home-analysis]');
    if (!button || button.dataset.bound) return;
    button.dataset.bound = '1';
    button.addEventListener('click', expandHomeAnalysis);
  }

  function bindHomeFeedFilter() {
    function applyFilter(root, filter) {
      var active = filter || 'all';
      root.setAttribute('data-active-feed-filter', active);
      root.querySelectorAll('[data-feed-filter]').forEach(function (button) {
        var selected = button.getAttribute('data-feed-filter') === active;
        button.classList.toggle('is-active', selected);
        button.setAttribute('aria-selected', selected ? 'true' : 'false');
      });
      root.querySelectorAll('[data-feed-bucket]').forEach(function (item) {
        var bucket = item.getAttribute('data-feed-bucket');
        var visible = active === 'all' || bucket === active;
        item.classList.toggle('is-filtered-out', !visible);
        item.setAttribute('aria-hidden', visible ? 'false' : 'true');
      });
    }

    document.querySelectorAll('[data-home-unified-feed]').forEach(function (root) {
      var filterBar = root.querySelector('[data-home-feed-filter]');
      if (!filterBar || filterBar.dataset.bound) return;
      filterBar.dataset.bound = '1';
      filterBar.querySelectorAll('[data-feed-filter]').forEach(function (button) {
        button.addEventListener('click', function () {
          applyFilter(root, button.getAttribute('data-feed-filter'));
          window.dispatchEvent(new CustomEvent('presek:feed-filter-used', {
            detail: { filter: button.getAttribute('data-feed-filter') || 'all' },
          }));
        });
      });
    });
  }

  function bindAnalizaNav() {
    function setActiveChip(selector) {
      document.querySelectorAll('[data-analiza-target]').forEach(function (button) {
        var active = button.getAttribute('data-analiza-target') === selector;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-current', active ? 'true' : 'false');
      });
    }

    function scrollToBand(selector) {
      var target = document.querySelector(selector);
      if (!target) return;
      if (target.tagName === 'DETAILS') {
        target.open = true;
      }
      setActiveChip(selector);
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    document.querySelectorAll('[data-analiza-target]').forEach(function (button) {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', function () {
        scrollToBand(button.getAttribute('data-analiza-target'));
      });
    });

    var tracked = Array.from(document.querySelectorAll('[data-analiza-target]'))
      .map(function (button) {
        var selector = button.getAttribute('data-analiza-target');
        var target = selector ? document.querySelector(selector) : null;
        return target ? { selector: selector, target: target } : null;
      })
      .filter(Boolean);

    if (!tracked.length) return;
    if (window.__presekAnalizaObserver) {
      window.__presekAnalizaObserver.disconnect();
    }
    var observer = new IntersectionObserver(function (entries) {
      var visible = entries
        .filter(function (entry) { return entry.isIntersecting; })
        .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; })[0];
      if (!visible) return;
      var match = tracked.find(function (item) { return item.target === visible.target; });
      if (match && match.selector) setActiveChip(match.selector);
    }, {
      rootMargin: '-18% 0px -62% 0px',
      threshold: [0.08, 0.22, 0.4],
    });
    tracked.forEach(function (item) { observer.observe(item.target); });
    window.__presekAnalizaObserver = observer;
  }

  function bindLeadFeedScroll() {
    document.querySelectorAll('[data-scroll-home-feed]').forEach(function (button) {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', function () {
        var feed = document.getElementById('home-unified-feed')
          || document.querySelector('[data-testid="news-feed"] .home-mobile-order-feed');
        feed?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        window.dispatchEvent(new CustomEvent('presek:scroll-to-feed'));
      });
    });
  }

  function initTrendingPaint() {
    var trendItems = readJson('presek-trending-data', []);
    var root = document.querySelector('[data-trending-strip]');
    if (!root || !Array.isArray(trendItems) || trendItems.length === 0) return;

    var mount = root.querySelector('[data-trending-mount]');
    if (!mount) return;

    function paint() {
      if (mount.dataset.ready === '1') return;
      mount.dataset.ready = '1';
      var frag = document.createDocumentFragment();
      for (var i = 0; i < trendItems.length; i++) {
        var item = trendItems[i];
        var link = document.createElement('a');
        link.href = item.href;
        link.className = 'trending-card';

        var chip = document.createElement('span');
        chip.className = 'trend-chip';
        chip.textContent = item.chip || '';

        var title = document.createElement('h3');
        title.className = 'trending-card-title';
        title.textContent = item.title || '';

        var source = document.createElement('p');
        source.className = 'trending-card-source';
        source.textContent = item.source || '';

        link.append(chip, title, source);
        frag.appendChild(link);
      }
      mount.appendChild(frag);
    }

    function maybePaint() {
      if (root.open) paint();
    }

    root.addEventListener('toggle', maybePaint);

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        if (entries.some(function (entry) { return entry.isIntersecting; })) {
          maybePaint();
          observer.disconnect();
        }
      }, { rootMargin: '200px' });
      observer.observe(root);
    }
  }

  function initLivePaint() {
    var wireItems = readJson('presek-live-data', []);
    var root = document.querySelector('[data-live-strip]');
    if (!root) return;

    var mount = root.querySelector('[data-live-mount]');
    if (!mount) return;

    var lang = root.dataset.lang || 'sr';

    function paintItem(item, isNew) {
      var link = document.createElement('a');
      link.href = item.href;
      link.className = 'home-live-item' + (isNew ? ' home-live-item-pulse' : '');

      var meta = document.createElement('div');
      meta.className = 'home-live-meta';

      var time = document.createElement('span');
      time.textContent = item.time || '';

      var source = document.createElement('strong');
      source.textContent = item.source || '';

      meta.append(time, source);

      var title = document.createElement('p');
      title.textContent = item.title || '';

      link.append(meta, title);
      return link;
    }

    function paint() {
      if (mount.dataset.ready === '1') return;
      mount.dataset.ready = '1';
      var frag = document.createDocumentFragment();
      for (var i = 0; i < wireItems.length; i++) {
        frag.appendChild(paintItem(wireItems[i], false));
      }
      mount.appendChild(frag);
    }

    function maybePaint() {
      if (root.open) paint();
    }

    root.addEventListener('toggle', maybePaint);

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        if (entries.some(function (entry) { return entry.isIntersecting; })) {
          maybePaint();
          observer.disconnect();
        }
      }, { rootMargin: '160px' });
      observer.observe(root);
    }

    // Connect to SSE stream
    if (window.EventSource && !root.dataset.liveConnected) {
      root.dataset.liveConnected = '1';
      var source = new EventSource('/api/live');
      
      // Keep track of connection for cleanup on Astro page transitions
      var onPageUnload = function () {
        source.close();
        document.removeEventListener('astro:before-swap', onPageUnload);
      };
      document.addEventListener('astro:before-swap', onPageUnload);

      source.onmessage = function (event) {
        try {
          var payload = JSON.parse(event.data);
          if (payload && payload.type === 'new_article') {
            var prefix = lang === 'mk' ? '/mk' : '';
            var item = {
              href: prefix + '/cluster/' + payload.cluster_id,
              time: lang === 'mk' ? 'Сега' : 'Sada',
              source: payload.source || '',
              title: payload.title || ''
            };

            // 1. Add to beginning of wireItems array
            wireItems.unshift(item);

            // 2. Prepend to DOM if already painted
            if (mount.dataset.ready === '1') {
              var element = paintItem(item, true);
              mount.insertBefore(element, mount.firstChild);
            }

            // 3. Update summary badge and teaser
            var countEl = root.querySelector('.home-live-count');
            if (countEl) {
              countEl.textContent = Number(countEl.textContent || 0) + 1;
            }
            var teaserEl = root.querySelector('.home-live-summary-teaser');
            if (teaserEl) {
              var newLabel = lang === 'mk' ? '[НОВО]' : '[NOVO]';
              teaserEl.textContent = newLabel + ' ' + item.source + ': ' + item.title;
            }

            // 4. Fire a beautiful glassmorphic toast notification
            showLiveToast(item, lang);
          }
        } catch (e) {
          console.warn('[SSE-Live] Error handling message:', e);
        }
      };

      source.onerror = function () {
        // Soft close, let EventSource automatic reconnect handle it
      };
    }
  }

  function showLiveToast(item, lang) {
    var container = document.getElementById('presek-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'presek-toast-container';
      document.body.appendChild(container);
    }

    var toast = document.createElement('div');
    toast.className = 'presek-toast';

    var header = document.createElement('div');
    header.className = 'presek-toast-header';

    var meta = document.createElement('span');
    meta.className = 'presek-toast-meta';
    meta.textContent = lang === 'mk' ? '📡 Нова Вест' : '📡 Nova Vest';

    var source = document.createElement('span');
    source.className = 'presek-toast-source';
    source.textContent = item.source || '';

    header.append(meta, source);

    var body = document.createElement('p');
    body.className = 'presek-toast-body';
    body.textContent = item.title || '';

    toast.append(header, body);

    // Make toast clickable to navigate directly
    toast.style.cursor = 'pointer';
    toast.addEventListener('click', function () {
      window.location.href = item.href;
    });

    container.appendChild(toast);

    // Trigger exit animation after 5.5s
    setTimeout(function () {
      toast.classList.add('toast-exit');
      // Remove from DOM after exit transition
      setTimeout(function () {
        toast.remove();
      }, 400);
    }, 5500);
  }

  function initAnalysisBandsPaint() {
    var payload = readJson('presek-analysis-bands-data', null);
    if (!payload) return;

    var perspectiveItems = payload.perspectiveItems || [];
    var radarItems = payload.radarItems || [];
    var consensusItems = payload.consensusItems || [];
    var labels = payload.labels || {};

    function tierFill(value) {
      if (value >= 75) return 'linear-gradient(90deg, #a855f7, #db2777)';
      if (value >= 60) return 'linear-gradient(90deg, #14b8a6, #059669)';
      return 'linear-gradient(90deg, #0ea5e9, #4f46e5)';
    }

    function paintPerspectiveCard(item) {
      var card = document.createElement('div');
      card.className = 'analysis-card perspective-card';

      var top = document.createElement('div');
      var header = document.createElement('div');
      header.className = 'analysis-card-header';

      var eyebrow = document.createElement('span');
      eyebrow.className = 'analysis-eyebrow';
      eyebrow.textContent = item.category || 'Tema';

      var meterWrap = document.createElement('div');
      meterWrap.className = 'analysis-meter-wrap';

      var meter = document.createElement('div');
      meter.className = 'analysis-meter';
      var fill = document.createElement('div');
      fill.className = 'analysis-meter-fill';
      fill.style.width = (item.pluralism || 50) + '%';
      fill.style.background = tierFill(item.pluralism || 50);
      meter.appendChild(fill);

      var meterVal = document.createElement('span');
      meterVal.className = 'type-meta analysis-meter-value';
      meterVal.textContent = (item.pluralism || 50) + '%';

      meterWrap.append(meter, meterVal);
      header.append(eyebrow, meterWrap);
      top.appendChild(header);

      var link = document.createElement('a');
      link.href = item.href;
      link.className = 'analysis-card-title-link';
      var title = document.createElement('h3');
      title.className = 'type-card-title';
      title.textContent = item.title || '';
      link.appendChild(title);
      top.appendChild(link);

      var preview = document.createElement('p');
      preview.className = 'analysis-card-preview';
      preview.textContent = item.preview || '';
      top.appendChild(preview);

      var foot = document.createElement('div');
      foot.className = 'analysis-card-foot';
      var footLabel = document.createElement('span');
      footLabel.className = 'analysis-foot-label';
      footLabel.textContent = labels.reporting || '';
      foot.appendChild(footLabel);

      var chips = document.createElement('div');
      chips.className = 'analysis-source-list';
      (item.sources || []).forEach(function (source) {
        var chip = document.createElement('span');
        chip.className = 'analysis-source-chip';
        chip.textContent = source;
        chips.appendChild(chip);
      });
      if ((item.extraSources || 0) > 0) {
        var extra = document.createElement('span');
        extra.className = 'analysis-source-extra';
        extra.textContent = '+' + item.extraSources;
        chips.appendChild(extra);
      }
      foot.appendChild(chips);

      card.append(top, foot);
      return card;
    }

    function paintRadarCard(item) {
      var card = document.createElement('div');
      card.className = 'analysis-card radar-card';

      var top = document.createElement('div');
      var header = document.createElement('div');
      header.className = 'analysis-card-header';

      var status = document.createElement('span');
      status.className = 'analysis-radar-status';
      status.textContent = labels.factsConfirmed || '';

      var eyebrow = document.createElement('span');
      eyebrow.className = 'analysis-eyebrow';
      eyebrow.textContent = item.source || labels.portalFallback || '';

      header.append(status, eyebrow);
      top.appendChild(header);

      var link = document.createElement('a');
      link.href = item.href;
      link.className = 'analysis-card-title-link is-radar';
      var title = document.createElement('h3');
      title.className = 'type-card-title';
      title.textContent = item.title || '';
      link.appendChild(title);
      top.appendChild(link);

      var preview = document.createElement('p');
      preview.className = 'analysis-card-preview is-radar';
      preview.textContent = item.preview || '';
      top.appendChild(preview);

      var foot = document.createElement('div');
      foot.className = 'analysis-card-foot is-radar';
      var footLabel = document.createElement('span');
      footLabel.className = 'analysis-foot-label';
      footLabel.textContent = labels.factCheckSource || '';
      var source = document.createElement('span');
      source.className = 'analysis-radar-source';
      source.textContent = item.source || labels.portalFallback || '';
      foot.append(footLabel, source);

      card.append(top, foot);
      return card;
    }

    function paintConsensusCard(item) {
      var wrap = document.createElement('div');
      wrap.className = 'consensus-item';

      var link = document.createElement('a');
      link.href = item.href;
      link.className = 'consensus-lazy-card';
      var title = document.createElement('h3');
      title.className = 'consensus-lazy-title';
      title.textContent = item.title || '';
      var preview = document.createElement('p');
      preview.className = 'consensus-lazy-preview';
      preview.textContent = item.preview || '';
      var meta = document.createElement('span');
      meta.className = 'consensus-lazy-meta';
      meta.textContent = item.category || '';
      link.append(title, preview, meta);
      wrap.appendChild(link);
      return wrap;
    }

    function paintMount(mount, items, painter) {
      if (!mount || mount.dataset.ready === '1' || !items || !items.length) return;
      mount.dataset.ready = '1';
      var frag = document.createDocumentFragment();
      for (var i = 0; i < items.length; i++) {
        frag.appendChild(painter(items[i]));
      }
      mount.appendChild(frag);
    }

    function bindBand(detailsSelector, mountSelector, items, painter, afterPaint) {
      var details = document.querySelector(detailsSelector);
      if (!details) return;
      var mount = details.querySelector(mountSelector);
      if (!mount) return;

      function maybePaint() {
        if (!details.open) return;
        paintMount(mount, items, painter);
        if (afterPaint) afterPaint(details);
      }

      details.addEventListener('toggle', maybePaint);

      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function (entries) {
          if (entries.some(function (entry) { return entry.isIntersecting; })) {
            maybePaint();
            observer.disconnect();
          }
        }, { rootMargin: '240px' });
        observer.observe(details);
      }
    }

    bindBand('[data-perspectives-band]', '[data-perspectives-mount]', perspectiveItems, paintPerspectiveCard);
    bindBand('[data-radar-band]', '[data-radar-mount]', radarItems, paintRadarCard);
    bindBand('[data-consensus-band]', '[data-consensus-mount]', consensusItems, paintConsensusCard, function (details) {
      var grid = details.querySelector('[data-consensus-mount]');
      var wrap = details.querySelector('[data-consensus-wrap]');
      if (!grid || !wrap || wrap.dataset.navBound === '1') return;
      wrap.dataset.navBound = '1';
      wrap.querySelector('[data-consensus-prev]')?.addEventListener('click', function () {
        grid.scrollBy({ left: -(grid.offsetWidth * 0.75), behavior: 'smooth' });
      });
      wrap.querySelector('[data-consensus-next]')?.addEventListener('click', function () {
        grid.scrollBy({ left: grid.offsetWidth * 0.75, behavior: 'smooth' });
      });
    });
  }

  function boot() {
    initHomepageSession();
    bindHomeModeDock();
    homeDetailsDefaults();
    homeExpandAnalysis();
    bindHomeFeedFilter();
    bindAnalizaNav();
    bindLeadFeedScroll();
    initTrendingPaint();
    initLivePaint();
    initAnalysisBandsPaint();
  }

  boot();
  document.addEventListener('astro:page-load', boot);
  window.addEventListener('resize', homeDetailsDefaults, { passive: true });
})();
