import React, { useMemo, useState } from 'react';
import { Copy, Download, KeyRound, RefreshCw, Upload, ShieldCheck, Info } from 'lucide-react';
import { useStore } from '@nanostores/react';
import { $syncToken, updateSyncToken } from '../lib/store.ts';
import {
  buildSyncTokenHeaders,
  exportSyncPayload,
  mergeSyncPayload,
} from '../lib/personalization.js';

type SyncState = 'idle' | 'working' | 'done' | 'error';

export default function AccountSyncIsland() {
  const token = useStore($syncToken);
  const [inputToken, setInputToken] = useState('');
  const [status, setStatus] = useState<SyncState>('idle');
  const [message, setMessage] = useState('');

  const hasToken = useMemo(() => (token || '').trim().length > 0, [token]);

  const createSyncKey = async () => {
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync/init', { method: 'POST' });
      if (!res.ok) throw new Error('init failed');
      const data = await res.json();
      updateSyncToken(data.token);
      setInputToken(data.token);
      setStatus('done');
      setMessage('Klucot za sinhronizacija e kreiran. Vasiot lokalen profil e podgotven za sinhronizacija medju uredi.');
    } catch {
      setStatus('error');
      setMessage('Ne mozev da kreiram kluc za sinhronizacija vo momentov.');
    }
  };

  const pushLocalProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || token || '').trim();
    if (!nextToken) return;
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: nextToken,
          profile: exportSyncPayload(),
        }),
      });
      if (!res.ok) throw new Error('push failed');
      const data = await res.json();
      mergeSyncPayload(data.profile);
      updateSyncToken(nextToken);
      setStatus('done');
      setMessage('Lokalniot profil e sinhroniziran so vasiot kluc za profil.');
    } catch {
      setStatus('error');
      setMessage('Ne mozev da ga ispratam ovoj profil vo momentov.');
    }
  };

  const pullRemoteProfile = async (targetToken?: string) => {
    const nextToken = (targetToken || inputToken || token || '').trim();
    if (!nextToken) return;
    setStatus('working');
    setMessage('');
    try {
      const res = await fetch('/api/profile/sync', {
        headers: buildSyncTokenHeaders(nextToken) as Record<string, string>,
      });
      if (!res.ok) throw new Error('pull failed');
      const data = await res.json();
      mergeSyncPayload(data.profile);
      updateSyncToken(nextToken);
      setInputToken(nextToken);
      setStatus('done');
      setMessage('Sinhroniziraniot profil e vcitan na ovoj ured.');
    } catch {
      setStatus('error');
      setMessage('Ne mozev da ga vcitam toj kluc za sinhronizacija.');
    }
  };

  const copyToken = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setStatus('done');
      setMessage('Klucot za sinhronizacija e kopiran.');
    } catch {
      setStatus('error');
      setMessage('Ne mozev da ga kopiram klucot za sinhronizacija.');
    }
  };

  return (
    <div className="account-sync-island">
      <div className="bg-zinc-900 dark:bg-black text-white p-6 rounded-xl shadow-xl border-l-4 border-nyt-accent">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-nyt-accent/20 p-2 rounded-lg">
            <KeyRound className="text-nyt-accent" size={24} />
          </div>
          <div>
            <h3 className="text-lg font-black font-sans uppercase tracking-tight">Sinhronizacija</h3>
            <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">Anonimen kluc za prenos na profilot</p>
          </div>
        </div>

        {!hasToken ? (
          <div className="space-y-6">
            <div className="bg-zinc-800/50 p-4 rounded-lg border border-zinc-700/50">
              <div className="flex gap-3">
                <ShieldCheck size={18} className="text-nyt-accent shrink-0" />
                <p className="text-xs text-zinc-300 leading-relaxed">
                  Presek ne bara registracija. Vasiot profil se cuva lokalno, no mozete da ga prenesete na drug ured so pomos na taen kluc.
                </p>
              </div>
            </div>

            <button
              onClick={createSyncKey}
              disabled={status === 'working'}
              className="w-full bg-nyt-accent hover:bg-nyt-accent/90 text-white font-black py-4 rounded-lg flex items-center justify-center gap-2 transition-all transform active:scale-[0.98]"
            >
              {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <KeyRound size={18} />}
              GENERIRAJ KLUC
            </button>

            <div className="relative py-4">
              <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-zinc-800"></span></div>
              <div className="relative flex justify-center text-[10px] uppercase font-black text-zinc-500 bg-zinc-900 dark:bg-black px-2">Ili vnesete postoecki</div>
            </div>

            <div className="space-y-3">
              <input
                type="text"
                placeholder="Vnesete ga vasiot kluc..."
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 text-white p-4 rounded-lg text-sm font-mono placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-nyt-accent/50"
              />
              <button
                onClick={() => pullRemoteProfile()}
                disabled={!inputToken.trim() || status === 'working'}
                className="w-full bg-zinc-100 hover:bg-white text-black font-black py-4 rounded-lg flex items-center justify-center gap-2 transition-all"
              >
                <Download size={18} />
                VCITAJ PROFIL
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="bg-zinc-800/80 p-4 rounded-lg border border-zinc-700">
              <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2">Vasiot taen kluc</p>
              <div className="flex items-center gap-3">
                <code className="flex-1 text-sm font-mono text-nyt-accent truncate">{token}</code>
                <button onClick={copyToken} className="text-zinc-400 hover:text-white transition-colors">
                  <Copy size={18} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => pushLocalProfile()}
                disabled={status === 'working'}
                className="flex-1 bg-nyt-accent/10 border border-nyt-accent/30 hover:bg-nyt-accent/20 text-nyt-accent font-black py-4 rounded-lg flex flex-col items-center justify-center gap-2 transition-all"
              >
                {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <Upload size={18} />}
                <span className="text-[10px] uppercase">Isprati sega</span>
              </button>
              <button
                onClick={() => pullRemoteProfile()}
                disabled={status === 'working'}
                className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-white font-black py-4 rounded-lg flex flex-col items-center justify-center gap-2 transition-all"
              >
                {status === 'working' ? <RefreshCw className="animate-spin" size={18} /> : <Download size={18} />}
                <span className="text-[10px] uppercase">Vcitaj od oblak</span>
              </button>
            </div>

            <div className="flex gap-3 bg-zinc-800/30 p-3 rounded-lg">
              <Info size={14} className="text-zinc-500 shrink-0" />
              <p className="text-[10px] text-zinc-400 leading-normal">
                Zacuvajte ga ovoj kluc. Ako ga izgubite, ne mozeme da vi ga vratime profilot bidejci ne sobirame licni podatoci.
              </p>
            </div>
          </div>
        )}

        {message && (
          <div className={`mt-6 p-4 rounded-lg text-xs font-bold ${status === 'error' ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-green-500/10 text-green-500 border border-green-500/20'}`}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}
