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
    ...pulse.sr,
    ...archive.sr,
    ...entity.sr,
    ...sources.sr,
    ...graph.sr,
    ...methodology.sr,
    ...analize.sr,
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
    ...pulse.mk,
    ...archive.mk,
    ...entity.mk,
    ...sources.mk,
    ...graph.mk,
    ...methodology.mk,
    ...analize.mk,
  },
} as const;
