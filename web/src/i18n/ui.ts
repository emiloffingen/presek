export { languages, defaultLang } from './config';
export type { Locale } from './config';

import { defaultLang } from './config';
import { nav } from './namespaces/nav';
import { home } from './namespaces/home';
import { cluster } from './namespaces/cluster';
import { briefing } from './namespaces/briefing';
import { news } from './namespaces/news';
import { settings } from './namespaces/settings';
import { about } from './namespaces/about';
import { common } from './namespaces/common';
import { search } from './namespaces/search';

export const ui = {
  sr: {
    ...nav.sr,
    ...home.sr,
    ...cluster.sr,
    ...briefing.sr,
    ...news.sr,
    ...settings.sr,
    ...about.sr,
    ...common.sr,
    ...search.sr,
  },
  mk: {
    ...nav.mk,
    ...home.mk,
    ...cluster.mk,
    ...briefing.mk,
    ...news.mk,
    ...settings.mk,
    ...about.mk,
    ...common.mk,
    ...search.mk,
  },
} as const;
