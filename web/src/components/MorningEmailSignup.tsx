import React, { useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { useTranslations } from '../i18n/utils';
import type { ui } from '../i18n/ui';
import { Mail, CheckCircle2, Loader2 } from 'lucide-react';

type Variant = 'default' | 'compact' | 'settings' | 'editorial';

function getCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(';').shift();
  return undefined;
}

export default function MorningEmailSignup({
  lang = 'sr',
  variant = 'default',
}: {
  lang?: keyof typeof ui;
  variant?: Variant;
}) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const t = useTranslations(lang);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;

    setStatus('loading');
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const csrfToken = getCookie('csrf_token');
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      const res = await fetch(`${apiBaseUrl()}/newsletter/subscribe`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ email, locale: lang }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        setStatus('success');
        setMessage(data.message);
      } else {
        setStatus('error');
        setMessage(data.message || t('newsletter.error'));
      }
    } catch {
      setStatus('error');
      setMessage(t('newsletter.error'));
    }
  };

  if (status === 'success') {
    const successClass =
      variant === 'editorial'
        ? 'morning-email-signup morning-email-signup--editorial is-success'
        : `morning-email-signup morning-email-signup--${variant} is-success`;

    return (
      <section className={successClass}>
        <div className="morning-email-signup__success">
          <CheckCircle2 className="text-nyt-accent mb-3" size={24} />
          <h3 className="font-serif font-black text-lg mb-2 tracking-tight">{t('newsletter.success')}</h3>
          <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed">
            {t('newsletter.success_description')}
          </p>
        </div>
      </section>
    );
  }

  if (variant === 'editorial') {
    return (
      <section className="morning-email-signup morning-email-signup--editorial">
        <header className="morning-email-signup__editorial-head">
          <p className="morning-email-signup__editorial-kicker">{t('newsletter.title')}</p>
          <h3 className="morning-email-signup__editorial-title">{t('newsletter.description')}</h3>
          <p className="morning-email-signup__editorial-lede">{t('newsletter.subdescription')}</p>
        </header>

        <form onSubmit={handleSubmit} className="morning-email-signup__editorial-form">
          <label className="morning-email-signup__editorial-field">
            <span className="sr-only">{t('newsletter.placeholder')}</span>
            <input
              type="email"
              required
              placeholder={t('newsletter.placeholder')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button type="submit" disabled={status === 'loading'} className="morning-email-signup__editorial-submit">
            {status === 'loading' ? <Loader2 size={14} className="animate-spin" /> : t('newsletter.button')}
          </button>
        </form>

        {status === 'error' && (
          <p className="morning-email-signup__editorial-error">{message}</p>
        )}

        <p className="morning-email-signup__editorial-note">{t('newsletter.disclaimer')}</p>
      </section>
    );
  }

  const shellClass =
    variant === 'settings'
      ? 'morning-email-signup morning-email-signup--settings'
      : variant === 'compact'
        ? 'morning-email-signup morning-email-signup--compact'
        : 'morning-email-signup morning-email-signup--default bg-secondary/30 p-6 border border-border/60 rounded-xl relative overflow-hidden group';

  return (
    <section className={shellClass}>
      <div className="relative z-10">
        <header className={variant === 'compact' ? 'mb-4' : 'mb-5 pb-4 border-b border-border/40'}>
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent block mb-2">
            {t('newsletter.title')}
          </span>
          <h3 className={variant === 'compact' ? 'font-serif text-2xl font-black italic leading-tight' : 'section-heading leading-tight tracking-tight'}>
            {t('newsletter.description')}
          </h3>
        </header>

        <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed mb-5">
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
            {status === 'loading' ? <Loader2 size={14} className="animate-spin" /> : t('newsletter.button')}
          </button>
        </form>

        <p className="text-[9px] text-muted-foreground mt-4 leading-relaxed opacity-60">
          {t('newsletter.disclaimer')}
        </p>
      </div>
    </section>
  );
}
