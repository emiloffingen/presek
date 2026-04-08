import React, { useState, useEffect } from 'react';

export const ConsentBanner: React.FC = () => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem('presek_cookie_consent');
    if (!consent) {
      // Show after a short delay to not block initial render
      const timer = setTimeout(() => setVisible(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const accept = () => {
    localStorage.setItem('presek_cookie_consent', 'accepted');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[100] p-4 md:p-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="max-w-4xl mx-auto bg-card border border-border shadow-2xl rounded-xl p-6 md:flex md:items-center md:justify-between gap-6">
        <div className="mb-4 md:mb-0">
          <h3 className="font-serif font-bold text-lg mb-1">Колачиња и приватност</h3>
          <p className="text-sm text-secondary-foreground leading-relaxed">
            Користиме колачиња за да ги персонализираме содржините и огласите (Google AdSense), 
            да овозможиме функции на социјалните медиуми и да го анализираме сообраќајот. 
            Прочитајте ја нашата <a href="/privacy" className="underline hover:text-nyt-accent">Политика за приватност</a>.
          </p>
        </div>
        <div className="flex gap-3 shrink-0">
          <button 
            onClick={accept}
            className="px-6 py-2 bg-foreground text-background font-sans text-xs font-black uppercase tracking-widest hover:bg-nyt-accent hover:text-white transition-colors rounded-lg"
          >
            Прифаќам
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConsentBanner;
