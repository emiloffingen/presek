import React, { useState } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { Mail, CheckCircle2, Loader2 } from 'lucide-react';

export default function NewsletterIsland() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !email.includes('@')) return;

    setStatus('loading');
    try {
      const API_URL = apiBaseUrl();
      const res = await fetch(`${API_URL}/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, locale: 'mk' }),
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
      setMessage('Грешка при поврзување.');
    }
  };

  if (status === 'success') {
    return (
      <section className="bg-secondary/30 p-6 border border-border/60 relative overflow-hidden animate-in fade-in duration-500">
        <div className="flex flex-col items-center text-center relative z-10">
          <CheckCircle2 className="text-nyt-accent mb-4" size={28} />
          <h3 className="font-serif font-black text-lg mb-3 tracking-tight">Успешно се пријавивте!</h3>
          <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed">
            Секое утро во 08:00 часот ќе го добивате најважниот пресек на вестите директно во вашето сандаче.
          </p>
        </div>
        <div className="absolute -right-4 -bottom-4 opacity-5">
           <Mail size={120} strokeWidth={1} />
        </div>
      </section>
    );
  }

  return (
    <section className="bg-secondary/30 p-6 border border-border/60 relative overflow-hidden group">
      <div className="relative z-10">
        <header className="mb-5 pb-4 border-b border-border/40">
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-nyt-accent block mb-2">ДНЕВЕН ПРЕГЛЕД</span>
          <h3 className="font-serif text-xl font-black leading-tight tracking-tight">Уреден преглед на денот низ објективот на плурализмот.</h3>
        </header>

        <p className="font-serif italic text-sm text-secondary-foreground leading-relaxed mb-6">
          Секое утро добивајте дистилиран сублимат на настаните што ја обликуваат јавната дебата.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
            <input
              type="email"
              required
              placeholder="Вашата е-пошта"
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
            className="w-full py-2.5 bg-foreground text-background hover:bg-nyt-accent hover:text-white font-sans text-[10px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2"
          >
            {status === 'loading' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              "ПРИЈАВИ СЕ"
            )}
          </button>
        </form>

        <p className="text-[9px] text-muted-foreground mt-4 leading-relaxed opacity-60">
          * Со пријавувањето се согласувате со нашите услови. Можете да се одјавите во секое време.
        </p>
      </div>
      
      <div className="absolute -right-4 -bottom-4 opacity-5 group-hover:opacity-10 transition-opacity">
        <Mail size={120} strokeWidth={1} />
      </div>
    </section>
  );
}
