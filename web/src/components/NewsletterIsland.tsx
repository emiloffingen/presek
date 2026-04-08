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
        body: JSON.stringify({ email }),
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
      <section className="rail-module bg-nyt-accent/5 border-nyt-accent/20 border p-6 rounded-lg animate-in fade-in duration-500">
        <div className="flex flex-col items-center text-center">
          <CheckCircle2 className="text-nyt-accent mb-3" size={32} />
          <h3 className="font-serif font-bold text-lg mb-2">Успешно се пријавивте!</h3>
          <p className="text-sm text-secondary-foreground leading-relaxed">
            Секое утро во 08:00 часот ќе го добивате најважниот пресек на вестите директно во вашето сандаче.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="rail-module border border-border p-6 rounded-lg bg-card">
      <div className="flex items-center gap-2 mb-4">
        <Mail size={16} className="text-nyt-accent" />
        <h3 className="font-sans text-[11px] font-black uppercase tracking-widest">Утрински Брифинг</h3>
      </div>
      <p className="font-serif text-base leading-snug mb-4">
        Добијте го најважниот пресек на денот, секое утро.
      </p>
      
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="relative">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Вашата е-пошта"
            required
            className="w-full px-4 py-2.5 bg-secondary/30 border border-border rounded-lg text-sm focus:outline-none focus:border-nyt-accent transition-colors"
          />
        </div>
        
        {status === 'error' && (
          <p className="text-[10px] font-bold text-nyt-red uppercase tracking-tight">{message}</p>
        )}

        <button
          type="submit"
          disabled={status === 'loading'}
          className="w-full py-2.5 bg-foreground text-background font-sans text-[11px] font-black uppercase tracking-widest rounded-lg hover:bg-nyt-accent hover:text-white transition-all flex items-center justify-center gap-2"
        >
          {status === 'loading' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            'ПРИЈАВИ СЕ'
          )}
        </button>
      </form>
      <p className="text-[9px] text-muted-foreground mt-4 leading-relaxed italic">
        * Со пријавувањето се согласувате со нашите услови за користење и политика за приватност. Можете да се одјавите во секое време.
      </p>
    </section>
  );
}
