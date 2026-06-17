(function presekMotion() {
  const initHeadlineReveal = () => {
    if (window._presekHeadlineObserver) {
      window._presekHeadlineObserver.disconnect();
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

    document.querySelectorAll('.headline, .editorial-headline, .lead-media-frame').forEach((el) => {
      observer.observe(el);
    });
    window._presekHeadlineObserver = observer;
  };

  document.addEventListener('astro:page-load', initHeadlineReveal);
  initHeadlineReveal();

  const initSpotlight = () => {
    const targets = Array.from(document.querySelectorAll('.premium-spotlight'));
    if (targets.length === 0 || window.matchMedia('(pointer: coarse)').matches) return;
    let pendingEvent = null;
    let ticking = false;
    const handleMouseMove = (e) => {
      pendingEvent = e;
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        if (!pendingEvent) return;
        for (const target of targets) {
          if (!(target instanceof HTMLElement)) continue;
          const rect = target.getBoundingClientRect();
          const x = pendingEvent.clientX - rect.left;
          const y = pendingEvent.clientY - rect.top;
          target.style.setProperty('--mouse-x', `${x}px`);
          target.style.setProperty('--mouse-y', `${y}px`);
        }
        ticking = false;
      });
    };
    if (window._spotlightHandler) {
      window.removeEventListener('mousemove', window._spotlightHandler);
    }
    window._spotlightHandler = handleMouseMove;
    window.addEventListener('mousemove', handleMouseMove);
  };
  document.addEventListener('astro:page-load', initSpotlight);
  initSpotlight();
})();
