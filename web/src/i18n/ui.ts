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
import { pulse } from './namespaces/pulse';
import { archive } from './namespaces/archive';
import { entity } from './namespaces/entity';
import { sources } from './namespaces/sources';
import { graph } from './namespaces/graph';
import { methodology } from './namespaces/methodology';
import { analize } from './namespaces/analize';
import { editorial } from './namespaces/editorial';

export const ui = {
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
    ...pulse.mk,
    ...archive.mk,
    ...entity.mk,
    ...sources.mk,
    ...graph.mk,
    ...methodology.mk,
    ...analize.mk,
    ...editorial.mk,
  },
} as const;
