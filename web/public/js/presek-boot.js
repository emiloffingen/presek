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

  function applyTheme() {
    var stored = typeof localStorage !== 'undefined' ? localStorage.getItem('theme') : null;
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var isDark = stored ? stored === 'dark' : (stored === null ? prefersDark : false);

    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.style.colorScheme = 'dark';
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.style.colorScheme = 'light';
    }

    var themeColor = isDark ? '#0b0d13' : '#fdfdfa';
    var lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
    var darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
    if (lightMeta) lightMeta.setAttribute('content', themeColor);
    if (darkMeta) darkMeta.setAttribute('content', themeColor);
  }

  applyTheme();
  document.addEventListener('astro:after-swap', applyTheme);
})();
