(function presekHome() {
  'use strict';

  var lastVisitIncrement = 0;

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
    // boot() + astro:page-load both fire on first load; don't double-count.
    var now = Date.now();
    if (now - lastVisitIncrement > 1500) {
      lastVisitIncrement = now;
      try {
        localStorage.setItem(visitKey, String(visits + 1));
      } catch (_) {}
    }
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
      // Banded (?banded=1) view wraps items in per-bucket bands; hide the whole
      // band (header/count/grid) and the mid-feed ad so no empty shells remain.
      root.querySelectorAll('[data-feed-band]').forEach(function (band) {
        var bucket = band.getAttribute('data-feed-band');
        var visible = active === 'all' || bucket === active;
        band.classList.toggle('is-filtered-out', !visible);
        band.setAttribute('aria-hidden', visible ? 'false' : 'true');
      });
      root.querySelectorAll('.home-feed-ad-break').forEach(function (ad) {
        ad.classList.toggle('is-filtered-out', active !== 'all');
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
      if (details.dataset.bandsBound === '1') return;
      details.dataset.bandsBound = '1';
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
    bindHomeFeedFilter();
    bindLeadFeedScroll();
    initAnalysisBandsPaint();
  }

  boot();
  document.addEventListener('astro:page-load', boot);
  window.addEventListener('resize', homeDetailsDefaults, { passive: true });
})();
