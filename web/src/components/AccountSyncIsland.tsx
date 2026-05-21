import React, { useMemo, useState } from 'react';
import { useStore } from '@nanostores/react';
import { $syncToken, updateSyncToken } from '../lib/store';
import { KeyRound, ShieldCheck, RefreshCw, Copy, Upload, Download, AlertCircle, Check } from 'lucide-react';

export default function AccountSyncIsland({ lang = 'sr' }: { lang?: string }) {
  const token = useStore($syncToken);
  const [inputToken, setInputToken] = useState('');
  const [status, setStatus] = useState<'idle' | 'working' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(false);

  const hasToken = useMemo(() => (token || '').trim().length > 0, [token]);

  const createSyncKey = async () => {
    setStatus('working');
    try {
      const res = await fetch('/api/profile/sync/init', { method: 'POST' });
      const data = await res.json();
      if (data.token) {
        updateSyncToken(data.token);
        setStatus('success');
        setMessage(lang === 'sr'
          ? 'Ključ za sinhronizaciju je kreiran. Vaš lokalni profil je pripremljen za sinhronizaciju između uređaja.'
          : 'Клучот за синхронизација е креиран. Вашиот локален профил е подготвен за синхронизација помеѓу уредите.');
      }
    } catch {
      setStatus('error');
      setMessage(lang === 'sr' ? 'Greška pri kreiranju ključa.' : 'Грешка при креирање на клучот.');
    }
  };

  const pushLocalProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || token || '').trim();
    if (!nextToken) return;
    setStatus('working');
    try {
      const res = await fetch('/api/profile/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${nextToken}` },
        body: JSON.stringify({ profile: JSON.parse(localStorage.getItem('presek_profile_v2') || '{}') })
      });
      if (res.ok) {
        setStatus('success');
        setMessage(lang === 'sr'
          ? 'Lokalni profil je sinhronizovan sa vašim ključem.'
          : 'Локалниот профил е синхронизиран со вашиот клуч.');
      }
    } catch {
      setStatus('error');
      setMessage(lang === 'sr' ? 'Greška pri slanju podataka.' : 'Грешка pri slanju podataka.');
    }
  };

  const pullRemoteProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || inputToken || token || '').trim();
    if (!nextToken) return;
    setStatus('working');
    try {
      const res = await fetch('/api/profile/sync', {
        headers: { 'Authorization': `Bearer ${nextToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('presek_profile_v2', JSON.stringify(data.profile));
        updateSyncToken(nextToken);
        setStatus('success');
        setMessage(lang === 'sr'
          ? 'Sinhronizovani profil je učitan na ovom uređaju.'
          : 'Синхронизираниот профил е вчитан на овој уред.');
        window.location.reload();
      }
    } catch {
      setStatus('error');
      setMessage(lang === 'sr' ? 'Greška pri preuzimanju profila.' : 'Грешка при преземање на профилот.');
    }
  };

  const copyToken = async () => {
    if (token) {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="premium-card passport-glow-card">
        <div className="flex items-center gap-3.5 mb-6">
          <div className="p-3 bg-nyt-accent/10 rounded-xl">
            <KeyRound className="text-nyt-accent" size={24} />
          </div>
          <div>
            <h3 className="text-base sm:text-lg font-black font-sans uppercase tracking-tight text-foreground">
              {lang === 'sr' ? 'Digitalni Pasoš' : 'Дигитален Пасош'}
            </h3>
            <p className="text-[10px] text-muted-foreground font-black uppercase tracking-wider">
              {lang === 'sr' ? 'Sinhronizacija profila' : 'Синхронизација на профилот'}
            </p>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-secondary/45 p-4 rounded-xl border border-border/50 flex gap-3">
            <ShieldCheck size={18} className="text-nyt-accent shrink-0 mt-0.5" />
            <p className="text-xs text-muted-foreground leading-relaxed">
              {lang === 'sr'
                ? 'Presek ne zahteva registraciju. Vaš profil se čuva lokalno na ovom pretraživaču, ali možete ga preneti na bilo koji drugi uređaj uz pomoć ovog anonimnog ključa.'
                : 'Пресек не бара регистрација. Вашиот профил се чува локално на овој прелистувач, но можете да го пренесете на кој било друг уред со помош на овој анонимен клуч.'}
            </p>
          </div>

          {!hasToken ? (
            <button
              onClick={createSyncKey}
              disabled={status === 'working'}
              className="w-full bg-nyt-accent hover:bg-nyt-accent/90 text-white font-black py-4 rounded-xl flex items-center justify-center gap-2 transition-all duration-300 transform hover:scale-[1.01] active:scale-[0.99] text-xs uppercase tracking-wider shadow-lg shadow-nyt-accent/15 cursor-pointer"
            >
              {status === 'working' ? <RefreshCw className="animate-spin" size={16} /> : <KeyRound size={16} />}
              <span>{lang === 'sr' ? 'Kreiraj ključ za sinhronizaciju' : 'Креирај клуч за синхронизација'}</span>
            </button>
          ) : (
            <div className="bg-secondary/45 p-4 rounded-xl border border-border/60">
              <p className="text-[9px] font-black text-muted-foreground uppercase tracking-widest mb-2">
                {lang === 'sr' ? 'Vaš tajni ključ' : 'Вашиот таен клуч'}
              </p>
              <div className="flex items-center gap-3 p-3 bg-background/55 border border-border/55 rounded-lg">
                <code className="flex-1 text-xs sm:text-sm font-mono text-nyt-accent truncate">{token}</code>
                <button
                  onClick={copyToken}
                  className="text-muted-foreground hover:text-foreground transition-colors p-1"
                  title={lang === 'sr' ? 'Kopiraj ključ' : 'Копирај клуч'}
                >
                  {copied ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
                </button>
              </div>

              <div className="flex flex-col sm:flex-row gap-3 mt-4 pt-4 border-t border-border/40">
                <button
                  onClick={() => pushLocalProfile()}
                  disabled={status === 'working'}
                  className="flex-1 bg-nyt-accent/10 border border-nyt-accent/30 hover:bg-nyt-accent/20 text-nyt-accent font-black py-3 rounded-lg flex items-center justify-center gap-2 transition-all text-[10px] uppercase tracking-wider cursor-pointer"
                >
                  {status === 'working' ? <RefreshCw className="animate-spin" size={14} /> : <Upload size={14} />}
                  <span>{lang === 'sr' ? 'Backup na server' : 'Резервна копија'}</span>
                </button>
                <button
                  onClick={() => pullRemoteProfile()}
                  disabled={status === 'working'}
                  className="flex-1 bg-background/60 hover:bg-background border border-border/50 text-foreground font-black py-3 rounded-lg flex items-center justify-center gap-2 transition-all text-[10px] uppercase tracking-wider cursor-pointer"
                >
                  {status === 'working' ? <RefreshCw className="animate-spin" size={14} /> : <Download size={14} />}
                  <span>{lang === 'sr' ? 'Učitaj sa servera' : 'Вчитај од сервер'}</span>
                </button>
              </div>

              <p className="mt-4 text-[9px] text-muted-foreground/60 italic text-center leading-normal">
                {lang === 'sr'
                  ? 'Sačuvajte ovaj ključ na sigurnom mestu. Ako ga izgubite, ne možemo da vam vratimo profil jer ne čuvamo vaše lične podatke.'
                  : 'Зачувајте го овој клуч на безбедно место. Ако го изгубите, не можеме да ви го вратиме профилот бидејќи не ги чуваме вашите лични податоци.'}
              </p>
            </div>
          )}

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border/40"></span>
            </div>
            <div className="relative flex justify-center text-[9px] uppercase font-black text-muted-foreground/60 bg-transparent px-2 tracking-widest">
              {lang === 'sr' ? 'Ili povežite postojeći' : 'Или поврзете постоечки'}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={inputToken}
              onChange={(e) => setInputToken(e.target.value)}
              placeholder={lang === 'sr' ? "Unesite tajni ključ..." : "Внесете го тајниот клуч..."}
              className="flex-1 bg-background/45 border border-border/60 text-foreground p-3 rounded-xl text-xs sm:text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-nyt-accent/30 focus:border-nyt-accent transition-all"
            />
            <button
              onClick={() => pullRemoteProfile(inputToken)}
              disabled={status === 'working' || !inputToken.trim()}
              className="bg-foreground text-background dark:bg-foreground dark:text-background hover:opacity-90 font-black px-6 py-3 rounded-xl transition-all disabled:opacity-50 text-[10px] sm:text-xs uppercase tracking-widest cursor-pointer"
            >
              {lang === 'sr' ? 'Učitaj' : 'Вчитај'}
            </button>
          </div>
        </div>

        {message && (
          <div className={`mt-5 p-3.5 rounded-xl text-xs font-bold flex items-center gap-2.5 ${
            status === 'error'
              ? 'bg-red-500/10 text-red-500 border border-red-500/20'
              : 'bg-green-500/10 text-green-500 border border-green-500/20'
          }`}>
            {status === 'error' ? <AlertCircle size={16} /> : <Check size={16} className="text-green-500" />}
            <span>{message}</span>
          </div>
        )}
      </div>
    </div>
  );
}
