import React, { useEffect, useState } from 'react';
import { ArrowUpRight, Headphones, Newspaper } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';
import { localePathForLang } from '../lib/localePaths';

function extractBriefingTitle(content: string) {
  const line = String(content || '')
    .split('\n')
    .map((row) => row.trim())
    .find((row) => row.startsWith('# '));
  return line ? line.replace(/^#\s+/, '').replace(/\*\*/g, '').trim() : '';
}

function extractBriefingLead(content: string) {
  let inBigPicture = false;
  for (const rawLine of String(content || '').split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.startsWith('##')) {
      inBigPicture = /velika slika|golemata slika/i.test(line);
      continue;
    }
    if (inBigPicture && !line.startsWith('#')) {
      return line.replace(/\*\*/g, '').slice(0, 220);
    }
  }
  return '';
}

export default function ForYouBriefingCard({ lang = 'sr' }: { lang?: string }) {
  const isMK = lang === 'mk';
  const [title, setTitle] = useState('');
  const [lead, setLead] = useState('');
  const [date, setDate] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function loadBriefing() {
      try {
        const res = await fetch(`${apiBaseUrl()}/intelligence/briefing?lang=${lang}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !data?.content) return;
        setTitle(extractBriefingTitle(data.content));
        setLead(extractBriefingLead(data.content));
        setDate(String(data.date || ''));
      } catch {
        // Non-blocking teaser
      }
    }
    loadBriefing();
    return () => {
      cancelled = true;
    };
  }, [lang]);

  const briefingHref = date
    ? `${localePathForLang('/briefing', isMK ? 'mk' : 'sr')}?date=${date}`
    : localePathForLang('/briefing', isMK ? 'mk' : 'sr');
  const audioHref = `${briefingHref}#audio`;

  return (
    <section className="for-you-briefing-card">
      <div className="for-you-briefing-copy">
        <span className="for-you-briefing-kicker">
          <Newspaper size={14} /> {isMK ? 'Уредничко издание' : 'Uredničko izdanje'}
        </span>
        <h3>{title || (isMK ? 'Дневен брифинг' : 'Dnevni brifing')}</h3>
        <p>{lead || (isMK ? 'Краток уреднички преглед на денот, со аудио верзија.' : 'Kratak urednički pregled dana, sa audio verzijom.')}</p>
      </div>
      <div className="for-you-briefing-actions">
        <a href={briefingHref} className="for-you-briefing-btn is-primary">
          {isMK ? 'Прочитај го брифингот' : 'Pročitaj brifing'} <ArrowUpRight size={14} />
        </a>
        <a href={audioHref} className="for-you-briefing-btn">
          <Headphones size={14} /> {isMK ? 'Слушај' : 'Slušaj'}
        </a>
      </div>
    </section>
  );
}
