import React, { useEffect, useState } from 'react';
import type { BriefingSection } from '../../utils/briefingFormatter';

type Props = {
  sections: BriefingSection[];
  lang?: string;
};

export default function BriefingSectionsRail({ sections, lang = 'sr' }: Props) {
  const isMK = lang === 'mk';
  const [activeId, setActiveId] = useState(sections[0]?.id ?? '');
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const sentinel = document.getElementById('briefing-article-start');
    if (!sentinel) {
      setRevealed(true);
      return;
    }

    const revealObserver = new IntersectionObserver(
      ([entry]) => {
        setRevealed(!entry.isIntersecting);
      },
      { rootMargin: '-12% 0px 0px 0px', threshold: 0 },
    );

    revealObserver.observe(sentinel);
    return () => revealObserver.disconnect();
  }, []);

  useEffect(() => {
    if (!sections.length) return;

    const headings = sections
      .map((section) => document.getElementById(section.id))
      .filter((node): node is HTMLElement => node instanceof HTMLElement);

    if (!headings.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target instanceof HTMLElement) {
          setActiveId(visible[0].target.id);
        }
      },
      { rootMargin: '-20% 0px -55% 0px', threshold: [0, 0.25, 0.5, 1] },
    );

    headings.forEach((heading) => observer.observe(heading));
    return () => observer.disconnect();
  }, [sections]);

  if (!sections.length) return null;

  return (
    <nav
      className={`briefing-sections-rail ${revealed ? 'is-revealed' : ''}`}
      aria-label={isMK ? 'Секции' : 'Sekcije'}
      aria-hidden={!revealed}
    >
      <p className="briefing-sections-rail__kicker">{isMK ? 'Секции' : 'Sekcije'}</p>
      <ol className="briefing-sections-rail__list">
        {sections.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              className={`briefing-sections-link ${activeId === section.id ? 'is-active' : ''}`}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                window.history.replaceState(null, '', `#${section.id}`);
              }}
            >
              <span className="briefing-sections-link__index">{String(section.index).padStart(2, '0')}</span>
              <span className="briefing-sections-link__title">{section.title}</span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
