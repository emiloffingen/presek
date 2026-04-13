import React, { useState, useEffect } from 'react';
import { MessageCircle, X } from 'lucide-react';
import AskPresekPanel from './AskPresekPanel';

const GLOBAL_SUGGESTIONS = [
  'Кои се најважните вести денес?',
  'Каде се согласуваат изворите?',
  'Што останува нејасно?',
];

export default function GlobalAskIsland() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="ask-global-fab"
        onClick={() => setOpen(true)}
        aria-label="Прашај го Пресек"
      >
        <MessageCircle size={16} />
        Прашај
      </button>

      {open && (
        <div className="ask-global-overlay" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="ask-global-modal">
            <div className="ask-global-modal-header">
              <h3 className="nyt-section-label flex items-center gap-2 text-foreground" style={{ margin: 0 }}>
                <MessageCircle size={14} /> ПРАШАЈ ГО ПРЕСЕК
              </h3>
              <button type="button" className="ask-global-modal-close" onClick={() => setOpen(false)}>
                <X size={14} />
              </button>
            </div>
            <AskPresekPanel
              clusterId="frontpage"
              suggestions={GLOBAL_SUGGESTIONS}
            />
          </div>
        </div>
      )}
    </>
  );
}
