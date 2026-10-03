export { languages, defaultLang } from './config';
export type { Locale } from './config';

import { defaultLang } from './config';
import { nav } from './namespaces/nav';
import { home } from './namespaces/home';
import { cluster } from './namespaces/cluster';
import { news } from './namespaces/news';
import { settings } from './namespaces/settings';
import { about } from './namespaces/about';
import { common } from './namespaces/common';
import { search } from './namespaces/search';
import { archive } from './namespaces/archive';
import { entity } from './namespaces/entity';
import { sources } from './namespaces/sources';
import { methodology } from './namespaces/methodology';
import { editorial } from './namespaces/editorial';

export const ui = {
  mk: {
    ...nav.mk,
    ...home.mk,
    ...cluster.mk,
    ...news.mk,
    ...settings.mk,
    ...about.mk,
    ...common.mk,
    ...search.mk,
    ...archive.mk,
    ...entity.mk,
    ...sources.mk,
    ...methodology.mk,
    ...editorial.mk,
  },
} as const;
