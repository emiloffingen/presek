(function presekBoot() {
  try {
    var savedScale = localStorage.getItem('text-scale') || '1';
    document.documentElement.style.setProperty('--text-scale', savedScale);
  } catch (e) {}

  try {
    var path = window.location.pathname || '';
    var isPregled = path === '/pregled' || path === '/mk/pregled';
    var isHome = path === '/' || path === '/mk' || path === '/mk/';
    document.documentElement.dataset.homepageMode = isPregled ? 'analiza' : 'vesti';
    if (isHome && !isPregled) {
      document.documentElement.dataset.page = 'home';
    } else {
      delete document.documentElement.dataset.page;
    }
  } catch (e) {}

  function updateThemeColor(isDark) {
    var themeColor = isDark ? '#0b0d13' : '#fdfdfa';
    var lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
    var darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
    if (lightMeta) lightMeta.setAttribute('content', themeColor);
    if (darkMeta) darkMeta.setAttribute('content', themeColor);
  }

  function updateThemeControls(theme) {
    var isDark = theme === 'dark';
    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      var nextLabel = isDark
        ? button.getAttribute('data-label-light') || 'Switch to light mode'
        : button.getAttribute('data-label-dark') || 'Switch to dark mode';
      button.setAttribute('aria-label', nextLabel);
      button.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      button.setAttribute('title', nextLabel);
      button.setAttribute('data-theme-state', theme);
    });
  }

  function setResolvedTheme(theme, persist) {
    var isDark = theme === 'dark';

    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      document.documentElement.style.colorScheme = 'dark';
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      document.documentElement.style.colorScheme = 'light';
    }

    if (persist) {
      try {
        localStorage.setItem('theme', theme);
      } catch (e) {}
    }

    updateThemeColor(isDark);
    updateThemeControls(theme);
  }

  function getStoredTheme() {
    try {
      var stored = typeof localStorage !== 'undefined' ? localStorage.getItem('theme') : null;
      return stored === 'dark' || stored === 'light' ? stored : null;
    } catch (e) {
      return null;
    }
  }

  function applyTheme() {
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var stored = getStoredTheme();
    setResolvedTheme(stored || (prefersDark ? 'dark' : 'light'), false);
  }

  window.presekApplyTheme = setResolvedTheme;
  applyTheme();
  document.addEventListener('click', function (event) {
    var toggle = event.target && event.target.closest ? event.target.closest('[data-theme-toggle]') : null;
    if (!toggle) return;
    var nextTheme = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
    setResolvedTheme(nextTheme, true);
  });
  document.addEventListener('DOMContentLoaded', applyTheme);
  document.addEventListener('astro:page-load', applyTheme);
  document.addEventListener('astro:after-swap', applyTheme);

  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (!getStoredTheme()) applyTheme();
    });
  } catch (e) {}

  window.addEventListener('storage', function (event) {
    if (event.key === 'theme') applyTheme();
  });
})();
