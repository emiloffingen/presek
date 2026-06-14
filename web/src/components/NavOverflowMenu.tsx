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
  const [focusIndex, setFocusIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }
      if (!panelRef.current) return;
      const links = Array.from(panelRef.current.querySelectorAll<HTMLAnchorElement>('a[role="menuitem"]'));
      if (!links.length) return;

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setFocusIndex((prev) => {
          const next = prev < 0 ? 0 : (prev + 1) % links.length;
          links[next]?.focus();
          return next;
        });
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setFocusIndex((prev) => {
          const next = prev <= 0 ? links.length - 1 : prev - 1;
          links[next]?.focus();
          return next;
        });
      } else if (event.key === 'Home') {
        event.preventDefault();
        links[0]?.focus();
        setFocusIndex(0);
      } else if (event.key === 'End') {
        event.preventDefault();
        links[links.length - 1]?.focus();
        setFocusIndex(links.length - 1);
      }
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      const first = panelRef.current?.querySelector<HTMLAnchorElement>('a[role="menuitem"]');
      first?.focus();
      setFocusIndex(0);
    } else {
      setFocusIndex(-1);
    }
  }, [open]);

  if (!items.length) return null;

  return (
    <div className="nav-rail-overflow" ref={rootRef}>
      <button
        ref={triggerRef}
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
        <div className="nav-overflow-panel" id={panelId} role="menu" ref={panelRef}>
          {items.map((item, index) => (
            <a
              key={`${item.href}-${item.label}`}
              href={localePathForLang(item.href, lang)}
              className="nav-rail-link nav-overflow-link"
              role="menuitem"
              tabIndex={focusIndex === index ? 0 : -1}
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
