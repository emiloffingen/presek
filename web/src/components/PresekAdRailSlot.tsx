import React, { useEffect, useState } from 'react';

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
      fetch(`/api/marketing/ads/${activeAd.id}/impression`, { method: 'POST' })
        .then(() => setImpressionLogged(true))
        .catch(err => console.error('Failed to log impression:', err));
    }
  }, [activeAd, impressionLogged]);

  const handleAdClick = () => {
    if (activeAd) {
      fetch(`/api/marketing/ads/${activeAd.id}/click`, { method: 'POST' })
        .catch(err => console.error('Failed to log click:', err));
    }
  };

  if (loading) {
    return <div className={`h-[250px] w-full bg-slate-900/10 border border-slate-800/80 rounded-xl animate-pulse ${className}`} />;
  }

  const isMk = lang === 'mk';
  const title = isMk ? 'Купете го овој рекламен простор' : 'Kupite ovaj reklamni prostor';
  const desc = isMk 
    ? 'Автоматизиран самопослужен систем за реклами со Stripe плаќање.' 
    : 'Automatski samouslužni sistem za reklame sa Stripe plaćanjem.';
  const priceStr = isMk 
    ? `Од 75 ден. / 1000 импресии` 
    : `Od 75 MKD / 1000 impresija`;
  const btnText = isMk ? 'Рекламирај се' : 'Oglašavaj se';
  const marketingUrl = isMk ? '/mk/marketing' : '/marketing';

  return (
    <div className={`native-ad-slot-react sidebar-placement ${className}`} style={{ minHeight: '250px', display: 'flex', width: '100%' }}>
      {activeAd ? (
        <div className="active-ad-container relative w-full h-full bg-black/5 dark:bg-white/5 border border-slate-800 rounded-xl p-1 flex items-center justify-center">
          <div className="ad-badge absolute top-1.5 left-2 bg-black/60 text-white text-[10px] font-bold uppercase px-1.5 py-0.5 rounded pointer-events-none z-10 tracking-wider">
            {isMk ? 'Реклама' : 'Oglas'}
          </div>
          <a 
            href={activeAd.target_url} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="ad-link block w-full text-center"
            onClick={handleAdClick}
          >
            <img src={activeAd.image_url} alt="Advertisement" className="ad-image max-w-full max-h-full object-contain mx-auto rounded" />
          </a>
        </div>
      ) : (
        <div className="fallback-ad-card relative overflow-hidden rounded-xl border border-slate-800/50 hover:border-indigo-500/35 bg-gradient-to-br from-slate-900/80 to-slate-950/95 text-white p-5 flex flex-col justify-between transition-all duration-300 shadow-lg w-full">
          <div className="fallback-glow absolute -top-1/2 -left-1/2 w-[200%] h-[200%] bg-[radial-gradient(circle,rgba(99,102,241,0.12)_0%,transparent_60%)] pointer-events-none" />
          <div className="fallback-content relative z-10 flex flex-col gap-1.5">
            <div className="fallback-kicker-wrap flex items-center gap-1.5 mb-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              <div className="fallback-kicker text-[9px] font-extrabold text-indigo-400 tracking-widest uppercase">
                {isMk ? 'СЛОБОДЕН РЕКЛАМЕН ПРОСТОР' : 'SLOBODAN REKLAMNI PROSTOR'} (300x250)
              </div>
            </div>
            <h4 className="fallback-title text-sm font-bold text-slate-100 m-0 leading-snug">
              {title}
            </h4>
            <p className="fallback-desc text-xs text-slate-400 m-0 leading-relaxed">
              {desc}
            </p>
          </div>
          <div className="fallback-footer relative z-10 flex items-center justify-between mt-4 gap-2 flex-wrap">
            <span className="fallback-price text-xs font-bold text-emerald-400 font-mono">
              {priceStr}
            </span>
            <a 
              href={marketingUrl} 
              className="fallback-btn bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-600 text-white text-[11px] font-bold py-1.5 px-3 rounded shadow transition-all hover:scale-[1.02] active:scale-95 text-decoration-none flex items-center gap-1"
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
