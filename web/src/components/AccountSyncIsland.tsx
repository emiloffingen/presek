import React, { useMemo, useState } from 'react';
import { useStore } from '@nanostores/react';
import { $syncToken, updateSyncToken } from '../lib/store';
import { KeyRound, ShieldCheck, RefreshCw, Copy, Upload, Download, AlertCircle } from 'lucide-react';

export default function AccountSyncIsland({ lang = 'sr' }: { lang?: string }) {
  const token = useStore($syncToken);
  const [inputToken, setInputToken] = useState('');
  const [status, setStatus] = useState<'idle' | 'working' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

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
      setMessage(lang === 'sr' ? 'Greška pri slanju podataka.' : 'Грешка при испраќање на податоците.');
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
      setStatus('success');
      setMessage(lang === 'sr' ? 'Ključ je kopiran!' : 'Клучот е копиран!');
      setTimeout(() => setStatus('idle'), 2000);
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl">
        <div className="p-8">
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 bg-nyt-accent/10 rounded-xl">
              <KeyRound className="text-nyt-accent" size={24} />
            </div>
            <div>
              <h3 className="text-lg font-black font-sans uppercase tracking-tight">{lang === 'sr' ? 'Sinhronizacija' : 'Синхронизација'}</h3>
              <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">{lang === 'sr' ? 'Anoniman ključ za prenos profila' : 'Анонимен клуч за пренос на профилот'}</p>
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-zinc-800/50 p-4 rounded-lg border border-zinc-700/50 flex gap-3">
                <ShieldCheck size={18} className="text-nyt-accent shrink-0" />
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {lang === 'sr' 
                    ? 'Presek ne zahteva registraciju. Vaš profil se čuva lokalno, ali možete da ga prenesete na drugi uređaj uz pomoć tajnog ključa.' 
                    : 'Пресек не бара регистрација. Вашиот профил се чува локално, но можете да го пренесете на друг уред со помош на таен клуч.'}
                </p>
            </div>

            {!hasToken ? (
              <button
                onClick={createSyncKey}
                disabled={status === 'working'}
                className="w-full bg-nyt-accent hover:bg-nyt-accent/90 text-white font-black py-4 rounded-lg flex items-center justify-center gap-2 transition-all transform active:scale-[0.98]"
              >
                {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <KeyRound size={18} />}
                {lang === 'sr' ? 'KREIRAJ SINHRONIZACIONI KLJUČ' : 'КРЕИРАЈ КЛУЧ ЗА СИНХРОНИЗАЦИЈА'}
              </button>
            ) : (
              <div className="bg-zinc-800/80 p-4 rounded-lg border border-zinc-700">
                <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2">{lang === 'sr' ? 'Vaš tajni ključ' : 'Вашиот таен клуч'}</p>
                <div className="flex items-center gap-3">
                  <code className="flex-1 text-sm font-mono text-nyt-accent truncate">{token}</code>
                  <button onClick={copyToken} className="text-zinc-400 hover:text-white transition-colors">
                    <Copy size={16} />
                  </button>
                </div>
                <div className="flex gap-2 mt-4 pt-4 border-t border-zinc-700/50">
                  <button
                    onClick={() => pushLocalProfile()}
                    disabled={status === 'working'}
                    className="flex-1 bg-nyt-accent/10 border border-nyt-accent/30 hover:bg-nyt-accent/20 text-nyt-accent font-black py-4 rounded-lg flex flex-col items-center justify-center gap-2 transition-all"
                  >
                    {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <Upload size={18} />}
                    <span className="text-[10px] uppercase tracking-widest">{lang === 'sr' ? 'Pošalji lokalno' : 'Испрати локално'}</span>
                  </button>
                  <button
                    onClick={() => pullRemoteProfile()}
                    disabled={status === 'working'}
                    className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-white font-black py-4 rounded-lg flex flex-col items-center justify-center gap-2 transition-all"
                  >
                    {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <Download size={18} />}
                    <span className="text-[10px] uppercase tracking-widest">{lang === 'sr' ? 'Preuzmi sa servera' : 'Преземи од серверот'}</span>
                  </button>
                </div>
                <p className="mt-4 text-[9px] text-zinc-500 italic text-center leading-tight">
                  {lang === 'sr' 
                    ? 'Sačuvajte ovaj ključ. Ako ga izgubite, ne možemo da vam vratimo profil jer ne čuvamo lične podatke.' 
                    : 'Зачувајте го овој клуч. Ако го изгубите, не можеме да ви го вратиме профилот бидејќи не чуваме лични податоци.'}
                </p>
              </div>
            )}

            <div className="relative">
              <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-zinc-800"></span></div>
              <div className="relative flex justify-center text-[10px] uppercase font-black text-zinc-500 bg-zinc-900 dark:bg-black px-2">{lang === 'sr' ? 'Ili unesite postojeći' : 'Или внесете постоечки'}</div>
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value)}
                placeholder={lang === 'sr' ? "Unesite tajni ključ..." : "Внесете го тајниот клуч..."}
                className="w-full bg-zinc-800 border border-zinc-700 text-white p-4 rounded-lg text-sm font-mono placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-nyt-accent/50"
              />
              <button
                onClick={() => pullRemoteProfile(inputToken)}
                disabled={status === 'working' || !inputToken.trim()}
                className="bg-zinc-100 hover:bg-white text-black font-black px-6 rounded-lg transition-all disabled:opacity-50"
              >
                {lang === 'sr' ? 'UČITAJ' : 'ВЧИТАЈ'}
              </button>
            </div>
          </div>

          {message && (
            <div className={`mt-6 p-4 rounded-lg text-xs font-bold flex items-center gap-3 ${status === 'error' ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-green-500/10 text-green-500 border border-green-500/20'}`}>
              {status === 'error' ? <AlertCircle size={16} /> : <RefreshCw size={16} />}
              {message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
