import React, { useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { useTranslations } from '../i18n/utils';
import type { ui } from '../i18n/ui';
import { Mail, CheckCircle2, Loader2 } from 'lucide-react';

export default function NewsletterIsland({ lang = 'sr' }: { lang?: keyof typeof ui }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const t = useTranslations(lang);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;

    setStatus('loading');
    try {
      const API_URL = apiBaseUrl();
      const res = await fetch(`${API_URL}/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, locale: lang }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        setStatus('success');
        setMessage(data.message);
      } else {
        setStatus('error');
        setMessage(data.message);
      }
    } catch (err) {
      setStatus('error');
      setMessage(t('newsletter.error'));
    }
  };

  if (status === 'success') {
    return (
      <section className="bg-secondary/30 p-6 border border-border/60 rounded-xl relative overflow-hidden animate-in fade-in duration-500">
        <div className="flex flex-col items-center text-center relative z-10">
          <CheckCircle2 className="text-nyt-accent mb-4" size={28} />
          <h3 className="font-serif font-black text-lg mb-3 tracking-tight">
            {t('newsletter.success')}
          </h3>
          <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed">
            {t('newsletter.success_description')}
          </p>
        </div>
        <div className="absolute -right-4 -bottom-4 opacity-5">
           <Mail size={120} strokeWidth={1} />
        </div>
      </section>
    );
  }

  return (
    <section className="bg-secondary/30 p-6 border border-border/60 rounded-xl relative overflow-hidden group">
      <div className="relative z-10">
        <header className="mb-5 pb-4 border-b border-border/40">
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent block mb-2">
            {t('newsletter.title')}
          </span>
          <h3 className="section-heading leading-tight tracking-tight">
            {t('newsletter.description')}
          </h3>
        </header>

        <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed mb-6">
          {t('newsletter.subdescription')}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-[var(--grid-gap)]">
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
            <input
              type="email"
              required
              placeholder={t('newsletter.placeholder')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 bg-background border border-border focus:border-nyt-accent outline-none font-sans text-sm transition-all"
            />
          </div>

          {status === 'error' && (
            <p className="text-[10px] font-bold text-nyt-red uppercase tracking-tight">{message}</p>
          )}

          <button
            type="submit"
            disabled={status === 'loading'}
            className="w-full py-2.5 bg-foreground text-background hover:bg-nyt-accent hover:text-white font-sans text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-[var(--grid-gap)]"
          >
            {status === 'loading' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              t('newsletter.button')
            )}
          </button>
        </form>

        <p className="text-[9px] text-muted-foreground mt-4 leading-relaxed opacity-60">
          {t('newsletter.disclaimer')}
        </p>
      </div>

      <div className="absolute -right-4 -bottom-4 opacity-5 group-hover:opacity-10 transition-opacity">
        <Mail size={120} strokeWidth={1} />
      </div>
    </section>
  );
}
