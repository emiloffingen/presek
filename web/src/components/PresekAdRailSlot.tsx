import React, { useEffect, useState } from 'react';
import { buildCsrfHeadersAsync } from '../lib/personalization';
import { CPM_RATES_EUR, CPM_BASE_EUR, PROMO_PERCENT, localCpm } from '../lib/adPricing';

interface Props {
  lang?: 'sr' | 'mk';
  className?: string;
}

interface Ad {
  id: string;
  image_url: string;
  target_url: string;
}

export default function PresekAdRailSlot({ lang = 'sr', className = '' }: Props) {
  const [activeAd, setActiveAd] = useState<Ad | null>(null);
  const [loading, setLoading] = useState(true);
  const [impressionLogged, setImpressionLogged] = useState(false);

  useEffect(() => {
    // Check if the current page path is an ad-free path
    const adFreePaths = ['/for-you', '/settings', '/briefing', '/marketing', '/mk/marketing'];
    const path = window.location.pathname;
    if (adFreePaths.some(p => path.endsWith(p))) {
      setLoading(false);
      return;
    }

    fetch('/api/marketing/ads/active')
      .then(res => {
        if (res.ok) return res.json();
        throw new Error('Failed to fetch');
      })
      .then(data => {
        const sidebarAds = data.ads?.sidebar || [];
        if (sidebarAds.length > 0) {
          setActiveAd(sidebarAds[Math.floor(Math.random() * sidebarAds.length)]);
        }
      })
      .catch(err => console.error('Active ads fetch error:', err))
      .finally(() => setLoading(false));
  }, []);

  // Track impression once when activeAd is visible and loaded
  useEffect(() => {
    if (activeAd && !impressionLogged) {
      let cancelled = false;
      buildCsrfHeadersAsync()
        .then((headers: Record<string, string>) =>
          fetch(`/api/marketing/ads/${activeAd.id}/impression`, {
            method: 'POST',
            headers,
            credentials: 'same-origin',
          }),
        )
        .then(() => {
          if (!cancelled) setImpressionLogged(true);
        })
        .catch((err: unknown) => console.error('Failed to log impression:', err));
      return () => {
        cancelled = true;
      };
    }
  }, [activeAd, impressionLogged]);

  const handleAdClick = () => {
    if (activeAd) {
      buildCsrfHeadersAsync()
        .then((headers: Record<string, string>) =>
          fetch(`/api/marketing/ads/${activeAd.id}/click`, {
            method: 'POST',
            headers,
            credentials: 'same-origin',
          }),
        )
        .catch((err: unknown) => console.error('Failed to log click:', err));
    }
  };

  if (loading) {
    return <div className={`h-[250px] w-full bg-[var(--surface-soft)] border border-[var(--border)] rounded-none animate-pulse ${className}`} />;
  }

  const isMk = lang === 'mk';
  const title = isMk ? 'Купете го овој рекламен простор' : 'Kupite ovaj reklamni prostor';
  const desc = isMk 
    ? 'Автоматизиран самопослужен систем за реклами со Stripe плаќање.' 
    : 'Automatski samouslužni sistem za reklame sa Stripe plaćanjem.';
  const cpm = CPM_RATES_EUR.sidebar;
  const cpmBase = CPM_BASE_EUR.sidebar;
  const local = localCpm(cpm, isMk ? 'mk' : 'sr');
  const btnText = isMk ? 'Рекламирај се' : 'Oglašavaj se';
  const marketingUrl = '/marketing';

  return (
    <div className={`native-ad-slot-react sidebar-placement ${className}`} style={{ minHeight: '250px', display: 'flex', width: '100%' }}>
      {activeAd ? (
        <div className="active-ad-container relative w-full h-full bg-black/5 dark:bg-white/5 border border-[var(--border)] rounded-none p-1 flex items-center justify-center">
          <div className="ad-badge absolute top-1.5 left-2 bg-[var(--foreground)] text-[var(--background)] text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-none pointer-events-none z-10 tracking-wider">
            {isMk ? 'Реклама' : 'Oglas'}
          </div>
          <a 
            href={activeAd.target_url} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="ad-link block w-full text-center"
            onClick={handleAdClick}
          >
            <img src={activeAd.image_url} alt="Advertisement" className="ad-image max-w-full max-h-full object-contain mx-auto rounded-none" />
          </a>
        </div>
      ) : (
        <div className="fallback-ad-card relative overflow-hidden rounded-none border border-[var(--border)] hover:border-[var(--foreground)] bg-[var(--surface-soft)] hover:bg-[var(--surface-strong)] text-[var(--foreground)] p-5 flex flex-col justify-between transition-all duration-300 w-full">
          <div className="fallback-content relative z-10 flex flex-col gap-1.5">
            <div className="fallback-kicker-wrap flex items-center gap-1.5 mb-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--nyt-red)] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[var(--nyt-red)]"></span>
              </span>
              <div className="fallback-kicker text-[9px] font-extrabold text-[var(--nyt-gray-500)] tracking-widest uppercase">
                {isMk ? 'СЛОБОДЕН РЕКЛАМЕН ПРОСТОР' : 'SLOBODAN REKLAMNI PROSTOR'} (300x250)
              </div>
            </div>
            <h4 className="fallback-title text-sm font-bold text-[var(--foreground)] m-0 leading-snug font-serif">
              {title}
            </h4>
            <p className="fallback-desc text-xs text-[var(--muted-foreground)] m-0 leading-relaxed">
              {desc}
            </p>
          </div>
          <div className="fallback-footer relative z-10 flex items-center justify-between mt-4 gap-2 flex-wrap">
            <span className="fallback-price flex flex-wrap items-baseline gap-1 font-mono">
              <span className="text-sm font-extrabold text-[var(--foreground)]">€{cpm.toFixed(2)}</span>
              <span className="text-[10px] text-[var(--muted-foreground)] line-through opacity-70">€{cpmBase.toFixed(2)}</span>
              <span className="text-[9px] font-extrabold px-1 text-white bg-[var(--presek-mark,#b91c1c)]">−{PROMO_PERCENT}%</span>
              <span className="text-[10px] text-[var(--muted-foreground)] w-full">~{local.amount} {local.currency} / 1000</span>
            </span>
            <a 
              href={marketingUrl} 
              className="fallback-btn bg-[var(--primary)] hover:bg-transparent text-[var(--primary-foreground)] hover:text-[var(--foreground)] border border-[var(--primary)] text-[11px] font-bold py-1.5 px-3 rounded-none transition-all duration-200 text-decoration-none flex items-center gap-1"
            >
              <span>{btnText}</span>
              <span>➔</span>
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
