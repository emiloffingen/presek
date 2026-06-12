import { useEffect } from 'react';

export default function HeaderScrollIsland() {
  useEffect(() => {
    const header = document.getElementById('main-header');
    if (!header) return;

    let lastY = window.scrollY;
    let ticking = false;

    const update = () => {
      const y = window.scrollY;
      const compact = y > 120;
      const hideTicker = y > 48;
      const scrollingUp = y < lastY;

      header.classList.toggle('header--compact', compact);
      header.classList.toggle('header--hide-ticker', hideTicker && !scrollingUp);
      header.classList.toggle('header--show-nav', scrollingUp && y > 120);

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
