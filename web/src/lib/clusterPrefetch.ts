const PREFETCHED = new Set<string>();

export function initClusterPrefetch() {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return;

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const link = entry.target as HTMLAnchorElement;
        const href = link.getAttribute('href');
        if (!href || PREFETCHED.has(href)) continue;
        PREFETCHED.add(href);
        fetch(href, { priority: 'low' } as RequestInit).catch(() => {});
        observer.unobserve(link);
      }
    },
    { rootMargin: '200px 0px' },
  );

  document.querySelectorAll<HTMLAnchorElement>('a[data-testid="cluster-link"]').forEach((link) => {
    observer.observe(link);
  });
}
