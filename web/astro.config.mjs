// @ts-nocheck
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';

// The public product is the Macedonian edition at presek.mk.
// https://astro.build/config
export default defineConfig({
  site: import.meta.env.PUBLIC_SITE_URL || 'https://presek.mk',
  trailingSlash: 'never',
  output: 'server',
  i18n: {
    defaultLocale: 'mk',
    locales: ['mk'],
    routing: {
      prefixDefaultLocale: false
    }
  },
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'viewport',
  },
  integrations: [
    react(),
    sitemap(),
  ],

  vite: {
    plugins: [tailwindcss()]
  },

  adapter: node({
    mode: 'standalone'
  }),
});
