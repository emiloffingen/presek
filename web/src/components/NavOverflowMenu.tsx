import React, { useEffect, useId, useRef, useState } from 'react';
import { localePathForLang, type Locale } from '../lib/localePaths';

type NavItem = {
  label: string;
  href: string;
};

interface Props {
  items: NavItem[];
  label: string;
  lang: Locale;
}

export default function NavOverflowMenu({ items, label, lang }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  if (!items.length) return null;

  return (
    <div className="nav-rail-overflow" ref={rootRef}>
      <button
        type="button"
        className="nav-overflow-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open && (
        <div className="nav-overflow-panel" id={panelId} role="menu">
          {items.map((item) => (
            <a
              key={`${item.href}-${item.label}`}
              href={localePathForLang(item.href, lang)}
              className="nav-rail-link nav-overflow-link"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <span className="link-label">{item.label.replace('#', '')}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
