import { useEffect } from 'react';

export default function HeaderScrollIsland() {
  useEffect(() => {
    const header = document.getElementById('main-header');
    if (!header) return;

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
        header.classList.toggle('header--show-nav', scrollingUp && y > 96);
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
    document.addEventListener('astro:page-load', update);

    return () => {
      window.removeEventListener('scroll', onScroll);
      document.removeEventListener('astro:page-load', update);
    };
  }, []);

  return null;
}
