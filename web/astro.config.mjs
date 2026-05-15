// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';
import partytown from '@astrojs/partytown';

// Site URL is determined dynamically in Layout.astro based on language
// https://astro.build/config
export default defineConfig({
  site: import.meta.env.PUBLIC_SITE_URL || 'https://presek.live',
  trailingSlash: 'never',
  output: 'server',
  i18n: {
    defaultLocale: 'sr',
    locales: ['sr', 'mk'],
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
    partytown({
      config: {
        forward: ['dataLayer.push', 'gtag'],
      },
    }),
  ],

  vite: {
    plugins: [tailwindcss()]
  },

  adapter: node({
    mode: 'standalone'
  })
});