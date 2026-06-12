import React, { useEffect, useState } from 'react';
import { useTranslations } from '../../i18n/utils';

export type FeedFilter = 'all' | 'developing' | 'global' | 'wire';

interface Props {
    lang?: string;
    counts: {
        all: number;
        developing: number;
        global: number;
        wire: number;
    };
}

const FILTERS: FeedFilter[] = ['all', 'developing', 'global', 'wire'];

export default function HomeFeedFilterIsland({ lang = 'sr', counts }: Props) {
    const t = useTranslations(lang as 'sr' | 'mk');
    const [active, setActive] = useState<FeedFilter>('all');

    const labels: Record<FeedFilter, string> = {
        all: t('home.feed_filter_all'),
        developing: t('home.feed_filter_developing'),
        global: t('home.feed_filter_global'),
        wire: t('home.feed_filter_wire'),
    };

    useEffect(() => {
        const root = document.querySelector('[data-home-unified-feed]');
        if (!root) return;

        root.setAttribute('data-active-feed-filter', active);
        root.querySelectorAll<HTMLElement>('[data-feed-bucket]').forEach((item) => {
            const bucket = item.getAttribute('data-feed-bucket');
            const visible = active === 'all' || bucket === active;
            item.classList.toggle('is-filtered-out', !visible);
            item.setAttribute('aria-hidden', visible ? 'false' : 'true');
        });
    }, [active]);

    useEffect(() => {
        const onPageLoad = () => setActive('all');
        document.addEventListener('astro:page-load', onPageLoad);
        return () => document.removeEventListener('astro:page-load', onPageLoad);
    }, []);

    return (
        <div className="home-feed-filter" role="tablist" aria-label={t('home.feed_filter_label')}>
            {FILTERS.map((filter) => {
                const count = counts[filter];
                if (filter !== 'all' && count === 0) return null;
                return (
                    <button
                        key={filter}
                        type="button"
                        role="tab"
                        aria-selected={active === filter}
                        className={`home-feed-filter-btn ${active === filter ? 'is-active' : ''}`}
                        onClick={() => setActive(filter)}
                    >
                        <span>{labels[filter]}</span>
                        <span className="home-feed-filter-count">{count}</span>
                    </button>
                );
            })}
        </div>
    );
}
